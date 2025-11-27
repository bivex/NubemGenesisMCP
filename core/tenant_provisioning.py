"""
Tenant Auto-Provisioning Module

Handles automatic tenant creation during OAuth signup flow.
Design approved by 6 L5 expert panel (see OAUTH_TENANT_INTEGRATION_EXPERT_DEBATE.md)

Key Features:
- Atomic tenant creation (tenant + quota + API key in 1 transaction)
- Race condition handling (duplicate email)
- Idempotency (same user multiple logins)
- Email validation
"""

import logging
import hashlib
import secrets
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from uuid import uuid4, UUID

from sqlalchemy import select, and_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.models import Tenant, TenantQuota, APIKey
from core.database.connection import get_db_session

logger = logging.getLogger(__name__)


# ============================================================================
# EMAIL VALIDATION
# ============================================================================

# Allowed email domains for tenant creation
# Set to None to allow any email domain
ALLOWED_EMAIL_DOMAINS = [
    '@nubemsystems.es',
    '@gmail.com',  # Allow Gmail for public access
    # Add more domains as needed
]

def is_email_allowed(email: str) -> bool:
    """
    Check if email domain is allowed for tenant creation.

    Args:
        email: User email address

    Returns:
        True if allowed, False otherwise
    """
    if ALLOWED_EMAIL_DOMAINS is None:
        # All domains allowed
        return True

    email = email.lower()

    for domain in ALLOWED_EMAIL_DOMAINS:
        if email.endswith(domain.lower()):
            return True

    logger.warning(f"Email domain not allowed: {email}")
    return False


# ============================================================================
# API KEY GENERATION
# ============================================================================

def generate_api_key() -> Tuple[str, str, str]:
    """
    Generate secure API key with hash and prefix.

    Security (approved by Raj Patel, CSO):
    - 256-bit random key (secrets.token_urlsafe)
    - SHA256 hash for storage (one-way)
    - Prefix for display (nsfc_xxx)

    Returns:
        Tuple of (full_key, key_hash, key_prefix)

    Example:
        >>> full_key, key_hash, key_prefix = generate_api_key()
        >>> full_key
        'nsfc_1Ab2Cd3Ef4Gh5Ij6Kl7Mn8Op9Qr0St1Uv2Wx3Yz'
        >>> key_prefix
        'nsfc_1Ab2Cd3'
    """
    # Generate 256-bit key
    raw_key = secrets.token_urlsafe(32)

    # Add prefix
    full_key = f"nsfc_{raw_key}"

    # Generate SHA256 hash for storage
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()

    # Extract prefix for display (first 7 chars after prefix)
    key_prefix = f"nsfc_{raw_key[:7]}"

    logger.debug(f"Generated API key with prefix: {key_prefix}")

    return full_key, key_hash, key_prefix


# ============================================================================
# TENANT AUTO-PROVISIONING
# ============================================================================

async def create_or_get_tenant_atomic(
    user_info: Dict,
    session: Optional[AsyncSession] = None
) -> Tuple[Tenant, Optional[str], bool]:
    """
    Atomically create tenant or get existing one.

    This function is IDEMPOTENT - calling it multiple times with the same
    email will NOT create duplicate tenants.

    Transaction scope (approved by Dr. Priya Patel):
    1. SELECT FOR UPDATE (prevent race condition)
    2. If exists → return existing tenant
    3. If NOT exists → CREATE tenant + quota + API key (atomic)

    Args:
        user_info: Dict with:
            - email (required): User email
            - email_verified (required): Must be True
            - name (optional): User display name
            - google_id (optional): Google user ID
            - picture (optional): Profile picture URL
        session: Optional database session (creates new if None)

    Returns:
        Tuple of (tenant, api_key, is_new)
        - tenant: Tenant object
        - api_key: Full API key (ONLY if newly created), None otherwise
        - is_new: True if tenant was just created, False if already existed

    Raises:
        ValueError: If email not verified or not allowed
        IntegrityError: If database constraint violation (handled internally)

    Example:
        >>> user_info = {
        ...     'email': 'user@example.com',
        ...     'email_verified': True,
        ...     'name': 'John Doe'
        ... }
        >>> tenant, api_key, is_new = await create_or_get_tenant_atomic(user_info)
        >>> if is_new:
        ...     print(f"New tenant created! API key: {api_key}")
        ... else:
        ...     print(f"Existing tenant: {tenant.id}")
    """
    # Validate email
    email = user_info['email'].lower()

    # Security check: Email must be verified by Google
    if not user_info.get('email_verified'):
        raise ValueError("Email not verified by Google")

    # Check if email domain is allowed
    if not is_email_allowed(email):
        raise ValueError(f"Email domain not authorized: {email}")

    # Get or create session
    if session is None:
        async with get_db_session() as session:
            return await _create_or_get_tenant_impl(session, user_info, email)
    else:
        return await _create_or_get_tenant_impl(session, user_info, email)


async def _create_or_get_tenant_impl(
    session: AsyncSession,
    user_info: Dict,
    email: str
) -> Tuple[Tenant, Optional[str], bool]:
    """
    Implementation of tenant creation/retrieval.

    Internal function - use create_or_get_tenant_atomic() instead.
    """
    try:
        # Step 1: Try to get existing tenant
        # SELECT FOR UPDATE prevents race condition
        stmt = select(Tenant).where(
            and_(
                func.lower(Tenant.email) == email,
                Tenant.deleted_at.is_(None)  # Only active tenants
            )
        ).with_for_update()

        result = await session.execute(stmt)
        existing_tenant = result.scalar_one_or_none()

        if existing_tenant:
            # Tenant exists - return it (no new API key)
            logger.info(f"Tenant exists for {email}: {existing_tenant.id}")
            return existing_tenant, None, False

        # Step 2: Create new tenant (doesn't exist)
        logger.info(f"Creating new tenant for {email}")

        tenant = Tenant(
            id=uuid4(),
            name=user_info.get('name', email.split('@')[0]),
            email=email,
            plan='free',  # Default plan for OAuth signups
            status='active',  # Instant activation (email verified by Google)
            max_requests_per_month=100,  # Free plan limit
            created_at=datetime.utcnow(),
            # OAuth-specific fields (optional)
            google_id=user_info.get('google_id'),
            picture_url=user_info.get('picture')
        )
        session.add(tenant)

        # Step 3: Create quota record
        quota = TenantQuota(
            tenant_id=tenant.id,
            requests_current_month=0,
            requests_last_month=0,
            tokens_input_current_month=0,
            tokens_output_current_month=0,
            created_at=datetime.utcnow()
        )
        session.add(quota)

        # Step 4: Generate API key
        full_key, key_hash, key_prefix = generate_api_key()

        api_key_record = APIKey(
            id=uuid4(),
            tenant_id=tenant.id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            role='admin',  # First user is admin
            is_active=True,
            name=f"Initial Key (OAuth - {user_info.get('name', 'User')})",
            created_at=datetime.utcnow(),
            last_used_at=None
        )
        session.add(api_key_record)

        # Step 5: Commit transaction (atomic)
        await session.commit()

        logger.info(f"✅ Created tenant {tenant.id} for {email}")
        logger.info(f"   - Plan: {tenant.plan}")
        logger.info(f"   - Quota: {tenant.max_requests_per_month} requests/month")
        logger.info(f"   - API Key: {key_prefix}...")

        # Return full API key (ONLY TIME user will see it)
        return tenant, full_key, True

    except IntegrityError as e:
        # Race condition: Another request created tenant between our SELECT and INSERT
        await session.rollback()

        logger.warning(f"Race condition detected for {email}: {e}")
        logger.info(f"Fetching tenant created by concurrent request...")

        # Get the tenant that was created by the other request
        stmt = select(Tenant).where(
            and_(
                func.lower(Tenant.email) == email,
                Tenant.deleted_at.is_(None)
            )
        )
        result = await session.execute(stmt)
        tenant = result.scalar_one()

        logger.info(f"✅ Fetched existing tenant {tenant.id} for {email} (race condition handled)")

        # Return tenant WITHOUT API key (it already exists)
        return tenant, None, False

    except Exception as e:
        # Any other error
        await session.rollback()
        logger.error(f"❌ Failed to create tenant for {email}: {e}", exc_info=True)
        raise


# ============================================================================
# TENANT LOOKUP
# ============================================================================

async def get_tenant_by_email(
    email: str,
    include_deleted: bool = False
) -> Optional[Tenant]:
    """
    Get tenant by email address.

    Args:
        email: Tenant email (case-insensitive)
        include_deleted: If True, include soft-deleted tenants

    Returns:
        Tenant object or None if not found
    """
    email = email.lower()

    async with get_db_session() as session:
        stmt = select(Tenant).where(
            func.lower(Tenant.email) == email
        )

        if not include_deleted:
            stmt = stmt.where(Tenant.deleted_at.is_(None))

        result = await session.execute(stmt)
        tenant = result.scalar_one_or_none()

        return tenant


async def get_tenant_by_id(
    tenant_id: UUID
) -> Optional[Tenant]:
    """
    Get tenant by ID.

    Args:
        tenant_id: Tenant UUID

    Returns:
        Tenant object or None if not found
    """
    async with get_db_session() as session:
        stmt = select(Tenant).where(
            and_(
                Tenant.id == tenant_id,
                Tenant.deleted_at.is_(None)
            )
        )

        result = await session.execute(stmt)
        tenant = result.scalar_one_or_none()

        return tenant


# ============================================================================
# STATISTICS
# ============================================================================

async def get_tenant_creation_stats() -> Dict:
    """
    Get tenant creation statistics.

    Returns:
        Dict with:
        - total_tenants: Total active tenants
        - tenants_today: Tenants created today
        - tenants_this_week: Tenants created this week
        - tenants_this_month: Tenants created this month
    """
    async with get_db_session() as session:
        now = datetime.utcnow()
        today_start = datetime(now.year, now.month, now.day)
        week_start = today_start - timedelta(days=now.weekday())
        month_start = datetime(now.year, now.month, 1)

        # Total active tenants
        total_stmt = select(func.count(Tenant.id)).where(
            Tenant.deleted_at.is_(None)
        )
        total_result = await session.execute(total_stmt)
        total_tenants = total_result.scalar()

        # Tenants created today
        today_stmt = select(func.count(Tenant.id)).where(
            and_(
                Tenant.created_at >= today_start,
                Tenant.deleted_at.is_(None)
            )
        )
        today_result = await session.execute(today_stmt)
        tenants_today = today_result.scalar()

        # Tenants created this week
        week_stmt = select(func.count(Tenant.id)).where(
            and_(
                Tenant.created_at >= week_start,
                Tenant.deleted_at.is_(None)
            )
        )
        week_result = await session.execute(week_stmt)
        tenants_this_week = week_result.scalar()

        # Tenants created this month
        month_stmt = select(func.count(Tenant.id)).where(
            and_(
                Tenant.created_at >= month_start,
                Tenant.deleted_at.is_(None)
            )
        )
        month_result = await session.execute(month_stmt)
        tenants_this_month = month_result.scalar()

        return {
            'total_tenants': total_tenants,
            'tenants_today': tenants_today,
            'tenants_this_week': tenants_this_week,
            'tenants_this_month': tenants_this_month
        }

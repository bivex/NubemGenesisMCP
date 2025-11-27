"""
Tenant Manager - Core business logic for multi-tenant operations
Manages tenant lifecycle, resource provisioning, and quota enforcement
"""

import os
import logging
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from core.database import (
    get_session, session_scope, set_tenant_context, reset_tenant_context,
    Tenant, APIKey, TenantQuota, TenantEvent, TenantSecret, UsageMetric
)

logger = logging.getLogger(__name__)


class TenantManagerError(Exception):
    """Base exception for TenantManager errors"""
    pass


class TenantAlreadyExistsError(TenantManagerError):
    """Raised when attempting to create a tenant that already exists"""
    pass


class TenantNotFoundError(TenantManagerError):
    """Raised when tenant is not found"""
    pass


class QuotaExceededError(TenantManagerError):
    """Raised when tenant exceeds their quota"""
    pass


class TenantManager:
    """
    Manages tenant lifecycle and operations

    Responsibilities:
    - Tenant CRUD operations
    - GCP project and K8s namespace provisioning
    - API key generation and management
    - Quota enforcement
    - Usage tracking
    - Audit logging
    """

    # Plan configurations
    PLAN_CONFIGS = {
        'free': {
            'max_requests_per_month': 100,
            'max_personas_active': 5,
            'max_api_keys': 1,
            'features': ['basic_personas', 'basic_mcps']
        },
        'pro': {
            'max_requests_per_month': 10000,
            'max_personas_active': 25,
            'max_api_keys': 5,
            'features': ['all_personas', 'all_mcps', 'priority_support']
        },
        'enterprise': {
            'max_requests_per_month': 100000,
            'max_personas_active': 100,
            'max_api_keys': 20,
            'features': ['all_personas', 'all_mcps', 'custom_personas', 'sla', 'dedicated_support']
        },
        'custom': {
            'max_requests_per_month': 999999999,
            'max_personas_active': 999,
            'max_api_keys': 50,
            'features': ['everything']
        }
    }

    def __init__(self, gcp_project_base: str = "nubemsfc-tenant", gcp_region: str = "us-central1"):
        """
        Initialize TenantManager

        Args:
            gcp_project_base: Base name for GCP projects (will append tenant ID)
            gcp_region: GCP region for resources
        """
        self.gcp_project_base = gcp_project_base
        self.gcp_region = gcp_region
        logger.info(f"TenantManager initialized (base: {gcp_project_base}, region: {gcp_region})")

    def create_tenant(
        self,
        name: str,
        email: str,
        plan: str = 'free',
        billing_email: Optional[str] = None,
        metadata: Optional[Dict] = None,
        trial_days: int = 14
    ) -> Tuple[Tenant, str]:
        """
        Create a new tenant with all necessary resources

        Args:
            name: Tenant/company name
            email: Primary contact email (must be unique)
            plan: Subscription plan (free/pro/enterprise/custom)
            billing_email: Billing contact email
            metadata: Additional metadata
            trial_days: Number of trial days (default 14)

        Returns:
            Tuple of (Tenant object, API key)

        Raises:
            TenantAlreadyExistsError: If email already exists
            TenantManagerError: For other errors
        """
        try:
            with session_scope() as session:
                # Check if tenant already exists
                existing = session.query(Tenant).filter_by(email=email).first()
                if existing:
                    raise TenantAlreadyExistsError(f"Tenant with email {email} already exists")

                # Get plan configuration
                plan_config = self.PLAN_CONFIGS.get(plan, self.PLAN_CONFIGS['free'])

                # Generate unique identifiers
                tenant_id = uuid4()
                gcp_project_id = f"{self.gcp_project_base}-{str(tenant_id)[:8]}"
                k8s_namespace = f"tenant-{str(tenant_id)[:8]}"

                # Create tenant
                tenant = Tenant(
                    id=tenant_id,
                    name=name,
                    email=email,
                    plan=plan,
                    status='trial' if trial_days > 0 else 'active',
                    gcp_project_id=gcp_project_id,
                    k8s_namespace=k8s_namespace,
                    max_requests_per_month=plan_config['max_requests_per_month'],
                    max_personas_active=plan_config['max_personas_active'],
                    max_api_keys=plan_config['max_api_keys'],
                    billing_email=billing_email or email,
                    trial_ends_at=datetime.utcnow() + timedelta(days=trial_days) if trial_days > 0 else None,
                    metadata=metadata or {}
                )

                session.add(tenant)
                session.flush()  # Get tenant ID

                # Initialize quota
                quota = TenantQuota(
                    tenant_id=tenant.id,
                    requests_count=0,
                    tokens_used=0,
                    requests_limit=plan_config['max_requests_per_month'],
                    tokens_limit=None,  # Optional token limit
                    is_quota_exceeded=False
                )
                session.add(quota)

                # Generate initial API key
                api_key, key_hash, key_prefix = self._generate_api_key()

                api_key_obj = APIKey(
                    tenant_id=tenant.id,
                    name="Initial API Key",
                    key_hash=key_hash,
                    key_prefix=key_prefix,
                    role='admin',
                    scopes=['read', 'write', 'admin'],
                    is_active=True
                )
                session.add(api_key_obj)

                # Log tenant creation event
                event = TenantEvent(
                    tenant_id=tenant.id,
                    event_type='tenant.created',
                    event_category='lifecycle',
                    actor_type='system',
                    actor_id='tenant_manager',
                    description=f"Tenant '{name}' created with plan '{plan}'",
                    metadata={
                        'plan': plan,
                        'trial_days': trial_days,
                        'gcp_project_id': gcp_project_id,
                        'k8s_namespace': k8s_namespace
                    }
                )
                session.add(event)

                session.commit()

                logger.info(f"✅ Tenant created: {tenant.id} ({email}) - Plan: {plan}")
                return tenant, api_key

        except IntegrityError as e:
            logger.error(f"Database integrity error creating tenant: {e}")
            raise TenantAlreadyExistsError(f"Tenant with email {email} already exists")
        except Exception as e:
            logger.error(f"Error creating tenant: {e}")
            raise TenantManagerError(f"Failed to create tenant: {e}")

    def get_tenant(
        self,
        tenant_id: Optional[UUID] = None,
        email: Optional[str] = None,
        include_deleted: bool = False
    ) -> Optional[Tenant]:
        """
        Get tenant by ID or email

        Args:
            tenant_id: Tenant UUID
            email: Tenant email
            include_deleted: Include soft-deleted tenants

        Returns:
            Tenant object or None if not found
        """
        try:
            with session_scope() as session:
                query = session.query(Tenant)

                if tenant_id:
                    query = query.filter(Tenant.id == tenant_id)
                elif email:
                    query = query.filter(Tenant.email == email)
                else:
                    raise ValueError("Must provide either tenant_id or email")

                if not include_deleted:
                    query = query.filter(Tenant.deleted_at.is_(None))

                tenant = query.first()
                return tenant

        except Exception as e:
            logger.error(f"Error getting tenant: {e}")
            return None

    def update_tenant(
        self,
        tenant_id: UUID,
        name: Optional[str] = None,
        plan: Optional[str] = None,
        status: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Tenant:
        """
        Update tenant information

        Args:
            tenant_id: Tenant UUID
            name: New name (optional)
            plan: New plan (optional)
            status: New status (optional)
            metadata: Metadata to merge (optional)

        Returns:
            Updated Tenant object

        Raises:
            TenantNotFoundError: If tenant not found
        """
        try:
            with session_scope() as session:
                tenant = session.query(Tenant).filter(
                    Tenant.id == tenant_id,
                    Tenant.deleted_at.is_(None)
                ).first()

                if not tenant:
                    raise TenantNotFoundError(f"Tenant {tenant_id} not found")

                changes = {}

                if name:
                    tenant.name = name
                    changes['name'] = name

                if plan:
                    old_plan = tenant.plan
                    tenant.plan = plan
                    plan_config = self.PLAN_CONFIGS.get(plan, self.PLAN_CONFIGS['free'])
                    tenant.max_requests_per_month = plan_config['max_requests_per_month']
                    tenant.max_personas_active = plan_config['max_personas_active']
                    tenant.max_api_keys = plan_config['max_api_keys']
                    changes['plan'] = {'old': old_plan, 'new': plan}

                    # Update quota limits
                    quota = session.query(TenantQuota).filter_by(tenant_id=tenant_id).first()
                    if quota:
                        quota.requests_limit = plan_config['max_requests_per_month']

                if status:
                    old_status = tenant.status
                    tenant.status = status
                    changes['status'] = {'old': old_status, 'new': status}

                if metadata:
                    tenant.metadata.update(metadata)
                    changes['metadata'] = metadata

                tenant.updated_at = datetime.utcnow()

                # Log update event
                event = TenantEvent(
                    tenant_id=tenant.id,
                    event_type='tenant.updated',
                    event_category='lifecycle',
                    actor_type='system',
                    actor_id='tenant_manager',
                    description=f"Tenant updated: {', '.join(changes.keys())}",
                    metadata={'changes': changes}
                )
                session.add(event)

                session.commit()

                logger.info(f"✅ Tenant updated: {tenant_id} - Changes: {changes}")
                return tenant

        except TenantNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error updating tenant: {e}")
            raise TenantManagerError(f"Failed to update tenant: {e}")

    def delete_tenant(self, tenant_id: UUID, hard_delete: bool = False) -> bool:
        """
        Delete tenant (soft delete by default)

        Args:
            tenant_id: Tenant UUID
            hard_delete: Permanently delete from database (use with caution!)

        Returns:
            True if successful

        Raises:
            TenantNotFoundError: If tenant not found
        """
        try:
            with session_scope() as session:
                tenant = session.query(Tenant).filter_by(id=tenant_id).first()

                if not tenant:
                    raise TenantNotFoundError(f"Tenant {tenant_id} not found")

                if hard_delete:
                    # Log before deletion
                    logger.warning(f"🔥 HARD DELETE: Tenant {tenant_id} ({tenant.email})")
                    session.delete(tenant)
                else:
                    # Soft delete
                    tenant.deleted_at = datetime.utcnow()
                    tenant.status = 'deleted'

                    # Log soft delete event
                    event = TenantEvent(
                        tenant_id=tenant.id,
                        event_type='tenant.deleted',
                        event_category='lifecycle',
                        actor_type='system',
                        actor_id='tenant_manager',
                        description=f"Tenant soft deleted",
                        metadata={'hard_delete': False}
                    )
                    session.add(event)

                    logger.info(f"✅ Tenant soft deleted: {tenant_id} ({tenant.email})")

                session.commit()
                return True

        except TenantNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error deleting tenant: {e}")
            raise TenantManagerError(f"Failed to delete tenant: {e}")

    def check_quota(self, tenant_id: UUID) -> Dict:
        """
        Check tenant quota status

        Args:
            tenant_id: Tenant UUID

        Returns:
            Dictionary with quota information

        Raises:
            QuotaExceededError: If quota is exceeded
        """
        try:
            with session_scope() as session:
                quota = session.query(TenantQuota).filter_by(tenant_id=tenant_id).first()

                if not quota:
                    raise TenantManagerError(f"Quota not found for tenant {tenant_id}")

                remaining = quota.requests_limit - quota.requests_count
                percentage = (quota.requests_count / quota.requests_limit * 100) if quota.requests_limit > 0 else 0

                result = {
                    'tenant_id': str(tenant_id),
                    'requests_count': quota.requests_count,
                    'requests_limit': quota.requests_limit,
                    'requests_remaining': max(0, remaining),
                    'usage_percentage': round(percentage, 2),
                    'is_exceeded': quota.is_quota_exceeded,
                    'reset_at': quota.reset_at.isoformat() if quota.reset_at else None
                }

                if quota.is_quota_exceeded:
                    raise QuotaExceededError(f"Tenant {tenant_id} has exceeded quota ({quota.requests_count}/{quota.requests_limit})")

                return result

        except QuotaExceededError:
            raise
        except Exception as e:
            logger.error(f"Error checking quota: {e}")
            raise TenantManagerError(f"Failed to check quota: {e}")

    def increment_usage(
        self,
        tenant_id: UUID,
        requests: int = 1,
        tokens_input: int = 0,
        tokens_output: int = 0,
        api_key_id: Optional[UUID] = None,
        personas_used: Optional[List[str]] = None,
        mcps_used: Optional[List[str]] = None,
        latency_ms: Optional[int] = None,
        error: bool = False
    ) -> bool:
        """
        Increment tenant usage for rate limiting and billing

        Args:
            tenant_id: Tenant UUID
            requests: Number of requests to increment
            tokens_input: Input tokens used
            tokens_output: Output tokens used
            api_key_id: API key used
            personas_used: List of persona names used
            mcps_used: List of MCP names used
            latency_ms: Response latency in milliseconds
            error: Whether request resulted in error

        Returns:
            True if successful
        """
        try:
            with session_scope() as session:
                # Update quota
                quota = session.query(TenantQuota).filter_by(tenant_id=tenant_id).first()
                if quota:
                    quota.requests_count += requests
                    quota.tokens_used += (tokens_input + tokens_output)
                    quota.updated_at = datetime.utcnow()

                    # Check if exceeded
                    if quota.requests_count >= quota.requests_limit:
                        quota.is_quota_exceeded = True
                        quota.quota_exceeded_at = datetime.utcnow()

                # Record usage metric
                tokens_total = tokens_input + tokens_output
                cost_usd = self._calculate_cost(tokens_input, tokens_output)

                metric = UsageMetric(
                    tenant_id=tenant_id,
                    requests_count=requests,
                    tokens_input=tokens_input,
                    tokens_output=tokens_output,
                    tokens_total=tokens_total,
                    cost_usd=cost_usd,
                    personas_used=personas_used,
                    mcps_used=mcps_used,
                    api_key_id=api_key_id,
                    avg_latency_ms=latency_ms,
                    error_count=1 if error else 0,
                    timestamp=datetime.utcnow()
                )
                session.add(metric)

                # Update API key last_used_at
                if api_key_id:
                    api_key = session.query(APIKey).filter_by(id=api_key_id).first()
                    if api_key:
                        api_key.last_used_at = datetime.utcnow()
                        api_key.request_count += requests

                session.commit()

                logger.debug(f"Usage incremented for tenant {tenant_id}: +{requests} requests, +{tokens_total} tokens")
                return True

        except Exception as e:
            logger.error(f"Error incrementing usage: {e}")
            return False

    def generate_api_key(
        self,
        tenant_id: UUID,
        name: str,
        role: str = 'member',
        scopes: Optional[List[str]] = None,
        expires_days: Optional[int] = None
    ) -> Tuple[str, APIKey]:
        """
        Generate new API key for tenant

        Args:
            tenant_id: Tenant UUID
            name: Key name/description
            role: Role (owner/admin/member/readonly)
            scopes: Permission scopes
            expires_days: Expiration in days (None = never expires)

        Returns:
            Tuple of (API key string, APIKey object)

        Raises:
            TenantManagerError: If tenant not found or max keys exceeded
        """
        try:
            with session_scope() as session:
                # Check tenant exists and get limits
                tenant = session.query(Tenant).filter_by(id=tenant_id).first()
                if not tenant:
                    raise TenantNotFoundError(f"Tenant {tenant_id} not found")

                # Check if max API keys reached
                key_count = session.query(APIKey).filter_by(
                    tenant_id=tenant_id,
                    revoked_at=None
                ).count()

                if key_count >= tenant.max_api_keys:
                    raise TenantManagerError(
                        f"Tenant has reached maximum API keys limit ({tenant.max_api_keys})"
                    )

                # Generate API key
                api_key, key_hash, key_prefix = self._generate_api_key()

                api_key_obj = APIKey(
                    tenant_id=tenant_id,
                    name=name,
                    key_hash=key_hash,
                    key_prefix=key_prefix,
                    role=role,
                    scopes=scopes or ['read'],
                    is_active=True,
                    expires_at=datetime.utcnow() + timedelta(days=expires_days) if expires_days else None
                )
                session.add(api_key_obj)

                # Log event
                event = TenantEvent(
                    tenant_id=tenant_id,
                    event_type='api_key.created',
                    event_category='security',
                    actor_type='system',
                    actor_id='tenant_manager',
                    description=f"API key '{name}' created with role '{role}'",
                    metadata={'key_id': str(api_key_obj.id), 'role': role, 'scopes': scopes}
                )
                session.add(event)

                session.commit()

                logger.info(f"✅ API key created for tenant {tenant_id}: {name} ({role})")
                return api_key, api_key_obj

        except (TenantNotFoundError, TenantManagerError):
            raise
        except Exception as e:
            logger.error(f"Error generating API key: {e}")
            raise TenantManagerError(f"Failed to generate API key: {e}")

    def _generate_api_key(self) -> Tuple[str, str, str]:
        """
        Generate API key, hash, and prefix

        Returns:
            Tuple of (full_key, key_hash, key_prefix)
        """
        # Generate random key: nsfc_<32 random bytes in base64url>
        random_bytes = secrets.token_urlsafe(32)
        api_key = f"nsfc_{random_bytes}"

        # Hash for database storage
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        # Prefix for display (nsfc_abc***)
        key_prefix = f"{api_key[:12]}***"

        return api_key, key_hash, key_prefix

    def _calculate_cost(self, tokens_input: int, tokens_output: int) -> float:
        """
        Calculate cost in USD for token usage

        Args:
            tokens_input: Input tokens
            tokens_output: Output tokens

        Returns:
            Cost in USD
        """
        # Anthropic Claude pricing (approximate)
        # Input: $3 per million tokens
        # Output: $15 per million tokens
        input_cost = (tokens_input / 1_000_000) * 3.0
        output_cost = (tokens_output / 1_000_000) * 15.0

        return round(input_cost + output_cost, 6)

    def get_usage_summary(self, tenant_id: UUID, days: int = 30) -> Dict:
        """
        Get usage summary for tenant

        Args:
            tenant_id: Tenant UUID
            days: Number of days to look back

        Returns:
            Dictionary with usage statistics
        """
        try:
            with session_scope() as session:
                since_date = datetime.utcnow() - timedelta(days=days)

                metrics = session.query(UsageMetric).filter(
                    UsageMetric.tenant_id == tenant_id,
                    UsageMetric.timestamp >= since_date
                ).all()

                if not metrics:
                    return {
                        'tenant_id': str(tenant_id),
                        'period_days': days,
                        'total_requests': 0,
                        'total_tokens': 0,
                        'total_cost_usd': 0.0,
                        'error_count': 0
                    }

                total_requests = sum(m.requests_count for m in metrics)
                total_tokens = sum(m.tokens_total for m in metrics)
                total_cost = sum(float(m.cost_usd or 0) for m in metrics)
                error_count = sum(m.error_count for m in metrics)

                return {
                    'tenant_id': str(tenant_id),
                    'period_days': days,
                    'total_requests': total_requests,
                    'total_tokens': total_tokens,
                    'total_cost_usd': round(total_cost, 2),
                    'error_count': error_count,
                    'avg_tokens_per_request': round(total_tokens / total_requests, 2) if total_requests > 0 else 0
                }

        except Exception as e:
            logger.error(f"Error getting usage summary: {e}")
            return {}

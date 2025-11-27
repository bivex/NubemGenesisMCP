"""
API Key Management Endpoints

RESTful API for API key CRUD operations.
Design approved by 5 L5 expert panel (see TENANT_API_EXPERT_DEBATE.md)

CRITICAL SECURITY (approved by Raj Patel, CSO):
"Full API key is returned ONLY ONCE, at creation time. This is how GitHub,
Stripe, AWS all work. Non-negotiable."

Endpoints:
- POST   /api/v1/tenants/{tenant_id}/api-keys           # Create API key
- GET    /api/v1/tenants/{tenant_id}/api-keys           # List API keys
- GET    /api/v1/tenants/{tenant_id}/api-keys/{key_id}  # Get API key details
- PUT    /api/v1/tenants/{tenant_id}/api-keys/{key_id}  # Update API key
- DELETE /api/v1/tenants/{tenant_id}/api-keys/{key_id}  # Revoke API key
"""

import logging
import hashlib
import secrets
from uuid import UUID

from fastapi import APIRouter, Request, Depends
from fastapi.exceptions import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.models import APIKey
from core.database.connection import get_db_session
from mcp_server.api.models import (
    APIKeyCreate,
    APIKeyUpdate,
    APIKeyResponse,
    APIKeyCreateResponse,
    APIKeyListResponse,
    ErrorResponse
)
from mcp_server.api.dependencies import (
    check_tenant_access,
    require_admin,
    PaginationParams,
    validate_tenant_exists,
    validate_api_key_exists,
    check_api_key_quota,
    create_error_response
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/api-keys", tags=["API Keys"])


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def generate_api_key() -> tuple[str, str, str]:
    """
    Generate API key with hash and prefix

    Security design (approved by Raj Patel + Marcus Rodriguez):
    1. Generate raw key: secrets.token_urlsafe(32) → 256-bit entropy
    2. Hash for storage: SHA256 (one-way)
    3. Extract prefix: first 10 chars (for UI display)

    Returns:
        tuple of (raw_key, key_hash, key_prefix)
    """
    # Generate secure random key
    raw_key = secrets.token_urlsafe(32)

    # Add prefix for easy identification
    full_key = f"nsfc_{raw_key}"

    # Hash for storage (SHA256)
    key_hash = hashlib.sha256(full_key.encode('utf-8')).hexdigest()

    # Extract prefix (first 10 chars after 'nsfc_')
    key_prefix = f"nsfc_{raw_key[:7]}"

    return full_key, key_hash, key_prefix


def api_key_to_response(api_key: APIKey) -> APIKeyResponse:
    """
    Convert APIKey model to APIKeyResponse

    SECURITY: Does NOT include full API key

    Args:
        api_key: APIKey ORM model

    Returns:
        APIKeyResponse Pydantic model
    """
    return APIKeyResponse(
        id=api_key.id,
        key_prefix=api_key.key_prefix,
        role=api_key.role,
        is_active=api_key.is_active,
        created_at=api_key.created_at,
        last_used_at=api_key.last_used_at,
        name=api_key.name
    )


# ============================================================================
# POST /api/v1/tenants/{tenant_id}/api-keys - Create API Key
# ============================================================================

@router.post(
    "",
    response_model=APIKeyCreateResponse,
    status_code=201,
    responses={
        201: {"description": "API key created"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
        404: {"model": ErrorResponse, "description": "Tenant not found"},
        422: {"model": ErrorResponse, "description": "Quota exceeded"}
    }
)
async def create_api_key(
    tenant_id: UUID,
    key_data: APIKeyCreate,
    request: Request
) -> APIKeyCreateResponse:
    """
    Create new API key

    **CRITICAL SECURITY** (approved by Raj Patel, CSO):
    - Full API key returned ONLY ONCE
    - After creation, only prefix is visible
    - If lost, user must revoke and create new key

    **RBAC**:
    - Super admin: Can create for any tenant
    - Tenant admin: Can create for own tenant only
    - Member: Cannot create (403)

    **Quota**:
    - Max 10 API keys per tenant (all plans)
    - Returns 422 if quota exceeded

    **Creates**:
    - API key with specified role (admin/member)
    - Optional friendly name for identification

    **Expert approval**: 5/5 experts approved
    """
    try:
        # Check access (RBAC - admin required)
        await check_tenant_access(request, tenant_id, required_role="admin")

        # Validate tenant exists
        await validate_tenant_exists(tenant_id)

        # Check quota (max 10 API keys)
        await check_api_key_quota(tenant_id)

        # Generate API key
        raw_key, key_hash, key_prefix = generate_api_key()

        async with get_db_session() as session:
            # Create API key
            api_key = APIKey(
                tenant_id=tenant_id,
                key_hash=key_hash,
                key_prefix=key_prefix,
                role=key_data.role,
                name=key_data.name,
                is_active=True
            )

            session.add(api_key)
            await session.commit()
            await session.refresh(api_key)

            logger.info(
                f"API key created: {api_key.id} for tenant {tenant_id}, "
                f"role={key_data.role}, prefix={key_prefix}"
            )

            # Return response with FULL API KEY (ONLY TIME)
            return APIKeyCreateResponse(
                id=api_key.id,
                api_key=raw_key,  # FULL KEY - ONLY RETURNED ONCE
                key_prefix=key_prefix,
                role=api_key.role,
                is_active=api_key.is_active,
                created_at=api_key.created_at,
                last_used_at=api_key.last_used_at,
                name=api_key.name,
                warning="Save this API key now. You won't be able to see it again."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating API key: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=create_error_response(
                error_code="internal_error",
                message="Failed to create API key",
                request_id=getattr(request.state, "request_id", "unknown")
            )
        )


# ============================================================================
# GET /api/v1/tenants/{tenant_id}/api-keys - List API Keys (Paginated)
# ============================================================================

@router.get(
    "",
    response_model=APIKeyListResponse,
    responses={
        200: {"description": "List of API keys"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
        404: {"model": ErrorResponse, "description": "Tenant not found"}
    }
)
async def list_api_keys(
    tenant_id: UUID,
    request: Request,
    pagination: PaginationParams = Depends(),
    is_active: bool | None = None
) -> APIKeyListResponse:
    """
    List API keys for tenant (paginated)

    **SECURITY**: Does NOT return full API keys, only prefixes

    **RBAC**:
    - Super admin: Can list for any tenant
    - Tenant admin/member: Can list for own tenant only

    **Pagination**:
    - Default page_size: 50
    - Max page_size: 100

    **Filtering**:
    - is_active: Filter by active status (optional)

    **Expert approval**: 5/5 experts approved
    """
    try:
        # Check access (RBAC - member can read)
        await check_tenant_access(request, tenant_id, required_role="member")

        # Validate tenant exists
        await validate_tenant_exists(tenant_id)

        async with get_db_session() as session:
            # Build query
            stmt = select(APIKey).where(APIKey.tenant_id == tenant_id)

            # Apply filter
            if is_active is not None:
                stmt = stmt.where(APIKey.is_active == is_active)

            # Count total items
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total_result = await session.execute(count_stmt)
            total_items = total_result.scalar()

            # Apply pagination
            stmt = stmt.offset(pagination.offset).limit(pagination.limit)

            # Order by created_at desc (newest first)
            stmt = stmt.order_by(APIKey.created_at.desc())

            # Execute query
            result = await session.execute(stmt)
            api_keys = result.scalars().all()

            # Convert to response models (WITHOUT full keys)
            key_responses = [api_key_to_response(k) for k in api_keys]

            # Create pagination metadata
            pagination_meta = pagination.create_pagination_response(total_items)

            return APIKeyListResponse(
                data=key_responses,
                pagination=pagination_meta
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing API keys: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=create_error_response(
                error_code="internal_error",
                message="Failed to list API keys",
                request_id=getattr(request.state, "request_id", "unknown")
            )
        )


# ============================================================================
# GET /api/v1/tenants/{tenant_id}/api-keys/{key_id} - Get API Key Details
# ============================================================================

@router.get(
    "/{key_id}",
    response_model=APIKeyResponse,
    responses={
        200: {"description": "API key details"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
        404: {"model": ErrorResponse, "description": "API key not found"}
    }
)
async def get_api_key(
    tenant_id: UUID,
    key_id: UUID,
    request: Request
) -> APIKeyResponse:
    """
    Get API key details

    **SECURITY**: Does NOT return full API key, only prefix

    **RBAC**:
    - Super admin: Can view any tenant's keys
    - Tenant admin/member: Can view own tenant's keys only

    **Expert approval**: 5/5 experts approved
    """
    try:
        # Check access (RBAC - member can read)
        await check_tenant_access(request, tenant_id, required_role="member")

        # Validate API key exists and belongs to tenant
        api_key = await validate_api_key_exists(tenant_id, key_id)

        # Return response WITHOUT full key
        return api_key_to_response(api_key)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting API key: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=create_error_response(
                error_code="internal_error",
                message="Failed to get API key",
                request_id=getattr(request.state, "request_id", "unknown")
            )
        )


# ============================================================================
# PUT /api/v1/tenants/{tenant_id}/api-keys/{key_id} - Update API Key
# ============================================================================

@router.put(
    "/{key_id}",
    response_model=APIKeyResponse,
    responses={
        200: {"description": "API key updated"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
        404: {"model": ErrorResponse, "description": "API key not found"}
    }
)
async def update_api_key(
    tenant_id: UUID,
    key_id: UUID,
    key_data: APIKeyUpdate,
    request: Request
) -> APIKeyResponse:
    """
    Update API key

    **RBAC**:
    - Super admin: Can update any tenant's keys
    - Tenant admin: Can update own tenant's keys only
    - Member: Cannot update (403)

    **Updateable Fields**:
    - is_active: Enable/disable API key (toggle)

    **Use Cases**:
    - Temporarily disable API key (set is_active=false)
    - Re-enable API key (set is_active=true)

    **Expert approval**: 5/5 experts approved
    """
    try:
        # Check access (RBAC - admin required)
        await check_tenant_access(request, tenant_id, required_role="admin")

        # Validate API key exists and belongs to tenant
        api_key = await validate_api_key_exists(tenant_id, key_id)

        async with get_db_session() as session:
            # Update is_active if provided
            if key_data.is_active is not None:
                old_status = api_key.is_active
                api_key.is_active = key_data.is_active

                action = "enabled" if key_data.is_active else "disabled"
                logger.info(
                    f"API key {key_id} {action} (was: {old_status})"
                )

            # Save changes
            session.add(api_key)
            await session.commit()
            await session.refresh(api_key)

            logger.info(f"API key updated: {key_id}")

            # Return response WITHOUT full key
            return api_key_to_response(api_key)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating API key: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=create_error_response(
                error_code="internal_error",
                message="Failed to update API key",
                request_id=getattr(request.state, "request_id", "unknown")
            )
        )


# ============================================================================
# DELETE /api/v1/tenants/{tenant_id}/api-keys/{key_id} - Revoke API Key
# ============================================================================

@router.delete(
    "/{key_id}",
    status_code=204,
    responses={
        204: {"description": "API key revoked"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
        404: {"model": ErrorResponse, "description": "API key not found"}
    }
)
async def delete_api_key(
    tenant_id: UUID,
    key_id: UUID,
    request: Request
) -> None:
    """
    Revoke API key

    **RBAC**:
    - Super admin: Can revoke any tenant's keys
    - Tenant admin: Can revoke own tenant's keys only
    - Member: Cannot revoke (403)

    **Soft Revoke** (approved by Dr. Priya Patel):
    - Sets is_active = false (instead of DELETE)
    - Key hash remains in database for audit
    - Key becomes unusable immediately
    - Can be restored by setting is_active = true

    **Security**:
    - Revoked keys rejected by authentication middleware
    - Instant effect (cached entries have TTL)

    **Expert approval**: 5/5 experts approved
    """
    try:
        # Check access (RBAC - admin required)
        await check_tenant_access(request, tenant_id, required_role="admin")

        # Validate API key exists and belongs to tenant
        api_key = await validate_api_key_exists(tenant_id, key_id)

        async with get_db_session() as session:
            # Soft revoke: set is_active = false
            api_key.is_active = False
            session.add(api_key)
            await session.commit()

            logger.info(f"API key revoked: {key_id} (tenant: {tenant_id})")

        # Return 204 No Content (success)
        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking API key: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=create_error_response(
                error_code="internal_error",
                message="Failed to revoke API key",
                request_id=getattr(request.state, "request_id", "unknown")
            )
        )

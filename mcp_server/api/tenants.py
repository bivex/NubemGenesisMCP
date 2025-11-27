"""
Tenant Management Endpoints

RESTful API for tenant CRUD operations.
Design approved by 5 L5 expert panel (see TENANT_API_EXPERT_DEBATE.md)

Endpoints:
- POST   /api/v1/tenants                    # Register new tenant
- GET    /api/v1/tenants                    # List tenants (admin only)
- GET    /api/v1/tenants/{tenant_id}        # Get tenant details
- PUT    /api/v1/tenants/{tenant_id}        # Update tenant
- DELETE /api/v1/tenants/{tenant_id}        # Soft delete tenant
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, Depends, Query, HTTPException
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.models import Tenant, APIKey, TenantQuota
from core.database.connection import get_db_session
from core.tenant_manager import TenantManager
from mcp_server.api.models import (
    TenantCreate,
    TenantUpdate,
    TenantResponse,
    TenantListResponse,
    ErrorResponse
)
from mcp_server.api.dependencies import (
    check_tenant_access,
    require_super_admin,
    require_admin,
    PaginationParams,
    validate_tenant_exists,
    check_duplicate_email,
    create_error_response
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/tenants", tags=["Tenants"])

# Initialize tenant manager
tenant_manager = TenantManager()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def tenant_to_response(tenant: Tenant) -> TenantResponse:
    """
    Convert Tenant model to TenantResponse

    Args:
        tenant: Tenant ORM model

    Returns:
        TenantResponse Pydantic model
    """
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        email=tenant.email,
        plan=tenant.plan,
        status=tenant.status,
        created_at=tenant.created_at,
        max_requests_per_month=tenant.max_requests_per_month,
        gcp_project_id=tenant.gcp_project_id,
        k8s_namespace=tenant.k8s_namespace
    )


# ============================================================================
# POST /api/v1/tenants - Register New Tenant
# ============================================================================

@router.post(
    "",
    response_model=TenantResponse,
    status_code=201,
    responses={
        201: {"description": "Tenant created successfully"},
        409: {"model": ErrorResponse, "description": "Duplicate email"},
        422: {"model": ErrorResponse, "description": "Validation error"}
    }
)
async def create_tenant(
    tenant_data: TenantCreate,
    request: Request
) -> TenantResponse:
    """
    Register a new tenant

    **Registration Flow** (approved by Alex Martinez + Elena Volkov):
    1. With invite code: Instant activation (status: 'active')
    2. Without invite code: Email verification required (status: 'pending_verification')

    **RBAC**:
    - Public endpoint (no authentication required for registration)
    - Super admin can also create tenants

    **Validation**:
    - Email must be unique (409 if duplicate)
    - Name: 1-255 characters
    - Plan: free/pro/enterprise

    **Creates**:
    - Tenant record
    - Initial quota record
    - First API key (admin role)

    **Expert approval**: 5/5 experts approved
    """
    try:
        # Check for duplicate email
        await check_duplicate_email(tenant_data.email)

        # Determine status based on invite code
        if tenant_data.invite_code:
            # TODO: Validate invite code (future implementation)
            # For MVP, accept any invite code as valid
            status = "active"
            logger.info(f"Tenant registration with invite code: {tenant_data.email}")
        else:
            status = "pending_verification"
            # TODO: Send verification email (future implementation)
            logger.info(f"Tenant registration pending verification: {tenant_data.email}")

        # Create tenant using TenantManager
        tenant, api_key = tenant_manager.create_tenant(
            name=tenant_data.name,
            email=tenant_data.email,
            plan=tenant_data.plan
        )

        # Update status if pending verification
        if status == "pending_verification":
            async with get_db_session() as session:
                tenant.status = status
                session.add(tenant)
                await session.commit()
                await session.refresh(tenant)

        logger.info(
            f"Tenant created: {tenant.id} ({tenant.email}), status={status}"
        )

        return tenant_to_response(tenant)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating tenant: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=create_error_response(
                error_code="internal_error",
                message="Failed to create tenant",
                request_id=getattr(request.state, "request_id", "unknown")
            )
        )


# ============================================================================
# GET /api/v1/tenants - List Tenants (Paginated)
# ============================================================================

@router.get(
    "",
    response_model=TenantListResponse,
    responses={
        200: {"description": "List of tenants"},
        403: {"model": ErrorResponse, "description": "Forbidden (not super admin)"}
    }
)
async def list_tenants(
    request: Request,
    pagination: PaginationParams = Depends(),
    status: Optional[str] = Query(None, description="Filter by status"),
    plan: Optional[str] = Query(None, description="Filter by plan"),
    _: None = Depends(require_super_admin)
) -> TenantListResponse:
    """
    List all tenants (paginated)

    **RBAC**:
    - Super admin only
    - Returns 403 for non-super-admin users

    **Pagination** (approved by Dr. Priya Patel):
    - Default page_size: 50
    - Max page_size: 100
    - Offset-based pagination

    **Filtering**:
    - status: Filter by status (active/suspended/pending_verification)
    - plan: Filter by plan (free/pro/enterprise)

    **Expert approval**: 5/5 experts approved
    """
    try:
        async with get_db_session() as session:
            # Build query
            stmt = select(Tenant).where(Tenant.deleted_at.is_(None))

            # Apply filters
            if status:
                stmt = stmt.where(Tenant.status == status)
            if plan:
                stmt = stmt.where(Tenant.plan == plan)

            # Count total items (for pagination)
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total_result = await session.execute(count_stmt)
            total_items = total_result.scalar()

            # Apply pagination
            stmt = stmt.offset(pagination.offset).limit(pagination.limit)

            # Order by created_at desc (newest first)
            stmt = stmt.order_by(Tenant.created_at.desc())

            # Execute query
            result = await session.execute(stmt)
            tenants = result.scalars().all()

            # Convert to response models
            tenant_responses = [tenant_to_response(t) for t in tenants]

            # Create pagination metadata
            pagination_meta = pagination.create_pagination_response(total_items)

            return TenantListResponse(
                data=tenant_responses,
                pagination=pagination_meta
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing tenants: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=create_error_response(
                error_code="internal_error",
                message="Failed to list tenants",
                request_id=getattr(request.state, "request_id", "unknown")
            )
        )


# ============================================================================
# GET /api/v1/tenants/{tenant_id} - Get Tenant Details
# ============================================================================

@router.get(
    "/{tenant_id}",
    response_model=TenantResponse,
    responses={
        200: {"description": "Tenant details"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
        404: {"model": ErrorResponse, "description": "Tenant not found"}
    }
)
async def get_tenant(
    tenant_id: UUID,
    request: Request
) -> TenantResponse:
    """
    Get tenant details

    **RBAC** (approved by Raj Patel):
    - Super admin: Can view any tenant
    - Tenant admin/member: Can view own tenant only
    - Returns 403 if trying to access other tenant

    **Expert approval**: 5/5 experts approved
    """
    try:
        # Check access (RBAC)
        await check_tenant_access(request, tenant_id, required_role="member")

        # Validate tenant exists
        tenant = await validate_tenant_exists(tenant_id)

        return tenant_to_response(tenant)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tenant: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=create_error_response(
                error_code="internal_error",
                message="Failed to get tenant",
                request_id=getattr(request.state, "request_id", "unknown")
            )
        )


# ============================================================================
# PUT /api/v1/tenants/{tenant_id} - Update Tenant
# ============================================================================

@router.put(
    "/{tenant_id}",
    response_model=TenantResponse,
    responses={
        200: {"description": "Tenant updated"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
        404: {"model": ErrorResponse, "description": "Tenant not found"},
        409: {"model": ErrorResponse, "description": "Duplicate email"}
    }
)
async def update_tenant(
    tenant_id: UUID,
    tenant_data: TenantUpdate,
    request: Request
) -> TenantResponse:
    """
    Update tenant

    **RBAC** (approved by Raj Patel):
    - Super admin: Can update any tenant
    - Tenant admin: Can update own tenant only
    - Member: Cannot update (403)

    **Updateable Fields**:
    - name: Tenant name
    - plan: Subscription plan (free/pro/enterprise)

    **Validation**:
    - Name: 1-255 characters (if provided)
    - Plan: free/pro/enterprise (if provided)

    **Note**: Plan changes update max_requests_per_month automatically

    **Expert approval**: 5/5 experts approved
    """
    try:
        # Check access (RBAC - admin required)
        await check_tenant_access(request, tenant_id, required_role="admin")

        # Validate tenant exists
        tenant = await validate_tenant_exists(tenant_id)

        async with get_db_session() as session:
            # Update fields if provided
            if tenant_data.name is not None:
                tenant.name = tenant_data.name

            if tenant_data.plan is not None:
                # Update plan
                old_plan = tenant.plan
                tenant.plan = tenant_data.plan

                # Update max_requests_per_month based on new plan
                plan_configs = TenantManager.PLAN_CONFIGS
                tenant.max_requests_per_month = plan_configs[tenant_data.plan]["max_requests_per_month"]

                logger.info(
                    f"Tenant {tenant_id} plan changed: {old_plan} → {tenant_data.plan}"
                )

            # Save changes
            session.add(tenant)
            await session.commit()
            await session.refresh(tenant)

            logger.info(f"Tenant updated: {tenant_id}")

            return tenant_to_response(tenant)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating tenant: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=create_error_response(
                error_code="internal_error",
                message="Failed to update tenant",
                request_id=getattr(request.state, "request_id", "unknown")
            )
        )


# ============================================================================
# DELETE /api/v1/tenants/{tenant_id} - Soft Delete Tenant
# ============================================================================

@router.delete(
    "/{tenant_id}",
    status_code=204,
    responses={
        204: {"description": "Tenant deleted"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
        404: {"model": ErrorResponse, "description": "Tenant not found"}
    }
)
async def delete_tenant(
    tenant_id: UUID,
    request: Request
) -> None:
    """
    Soft delete tenant

    **RBAC** (approved by Raj Patel):
    - Super admin: Can delete any tenant
    - Tenant admin: Can delete own tenant only
    - Member: Cannot delete (403)

    **Soft Delete** (approved by Dr. Priya Patel):
    - Sets deleted_at timestamp
    - Tenant becomes invisible in queries
    - Data retained for audit/recovery
    - RLS policies automatically exclude soft-deleted tenants

    **Cascading Effects**:
    - API keys remain but inaccessible (RLS)
    - Usage data retained for audit
    - Can be restored by setting deleted_at = NULL

    **Expert approval**: 5/5 experts approved
    """
    try:
        # Check access (RBAC - admin required)
        await check_tenant_access(request, tenant_id, required_role="admin")

        # Validate tenant exists
        tenant = await validate_tenant_exists(tenant_id)

        async with get_db_session() as session:
            # Soft delete: set deleted_at timestamp
            tenant.deleted_at = datetime.utcnow()
            session.add(tenant)
            await session.commit()

            logger.info(f"Tenant soft deleted: {tenant_id}")

        # Return 204 No Content (success)
        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting tenant: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=create_error_response(
                error_code="internal_error",
                message="Failed to delete tenant",
                request_id=getattr(request.state, "request_id", "unknown")
            )
        )

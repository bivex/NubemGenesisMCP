"""
FastAPI Dependencies for Tenant API

Authorization and validation dependencies.
Design approved by expert panel (see TENANT_API_EXPERT_DEBATE.md)

RBAC Matrix (approved by Raj Patel, CSO):
- Super Admin: Full access to all resources
- Tenant Admin: Full access to own tenant's resources
- Tenant Member: Read-only access to own tenant's resources
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import Request, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.models import Tenant, APIKey
from core.database.connection import get_db_session

logger = logging.getLogger(__name__)


# ============================================================================
# RBAC DEPENDENCIES
# ============================================================================

async def check_tenant_access(
    request: Request,
    tenant_id: UUID,
    required_role: str = "member"
) -> bool:
    """
    Check if current user has access to tenant

    RBAC Rules (approved by Raj Patel, CSO):
    1. Super admin can access everything
    2. Tenant must access own tenant only
    3. Role hierarchy: member < admin < super_admin

    Args:
        request: FastAPI request (with auth context)
        tenant_id: Tenant ID to access
        required_role: Minimum role required

    Returns:
        True if access granted

    Raises:
        HTTPException(403): If access denied
    """
    # Get auth context from middleware
    current_tenant_id = getattr(request.state, "tenant_id", None)
    current_role = getattr(request.state, "api_key_role", None)

    # Super admin can access everything
    if current_role == "super_admin":
        return True

    # Check if accessing own tenant
    if str(current_tenant_id) != str(tenant_id):
        logger.warning(
            f"Access denied: tenant {current_tenant_id} trying to access {tenant_id}"
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error": "forbidden",
                "message": "Cannot access other tenant's resources",
                "request_id": getattr(request.state, "request_id", "unknown")
            }
        )

    # Check role hierarchy
    roles_hierarchy = {"member": 0, "admin": 1, "super_admin": 2}
    user_role_level = roles_hierarchy.get(current_role, -1)
    required_role_level = roles_hierarchy.get(required_role, 0)

    if user_role_level < required_role_level:
        logger.warning(
            f"Insufficient permissions: {current_role} < {required_role}"
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error": "insufficient_permissions",
                "message": f"Requires {required_role} role",
                "request_id": getattr(request.state, "request_id", "unknown")
            }
        )

    return True


def require_admin(request: Request) -> None:
    """
    Dependency: Require admin or super_admin role

    Usage:
        @app.post("/tenants/{tenant_id}/api-keys")
        async def create_api_key(
            tenant_id: UUID,
            _: None = Depends(require_admin)
        ):
            ...
    """
    current_role = getattr(request.state, "api_key_role", None)

    if current_role not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "insufficient_permissions",
                "message": "Admin role required",
                "request_id": getattr(request.state, "request_id", "unknown")
            }
        )


def require_super_admin(request: Request) -> None:
    """
    Dependency: Require super_admin role

    Usage:
        @app.get("/tenants")
        async def list_tenants(
            _: None = Depends(require_super_admin)
        ):
            ...
    """
    current_role = getattr(request.state, "api_key_role", None)

    if current_role != "super_admin":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "insufficient_permissions",
                "message": "Super admin role required",
                "request_id": getattr(request.state, "request_id", "unknown")
            }
        )


# ============================================================================
# PAGINATION DEPENDENCIES
# ============================================================================

class PaginationParams:
    """
    Pagination parameters

    Design approved by Dr. Priya Patel (Database Expert):
    - Default page_size: 50
    - Max page_size: 100
    - Offset-based pagination (simple, good for <10k records)
    """

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number (1-indexed)"),
        page_size: int = Query(50, ge=1, le=100, description="Items per page (max 100)")
    ):
        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * page_size
        self.limit = page_size

    def create_pagination_response(self, total_items: int) -> dict:
        """
        Create pagination metadata

        Returns:
            dict with pagination info
        """
        total_pages = (total_items + self.page_size - 1) // self.page_size

        return {
            "page": self.page,
            "page_size": self.page_size,
            "total_items": total_items,
            "total_pages": total_pages,
            "has_next": self.page < total_pages,
            "has_prev": self.page > 1
        }


# ============================================================================
# VALIDATION HELPERS
# ============================================================================

async def validate_tenant_exists(tenant_id: UUID) -> Tenant:
    """
    Validate tenant exists and is not soft deleted

    Args:
        tenant_id: Tenant UUID

    Returns:
        Tenant object

    Raises:
        HTTPException(404): If tenant not found or soft deleted
    """
    async with get_db_session() as session:
        stmt = select(Tenant).where(
            Tenant.id == tenant_id,
            Tenant.deleted_at.is_(None)  # Not soft deleted
        )
        result = await session.execute(stmt)
        tenant = result.scalar_one_or_none()

        if not tenant:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "resource_not_found",
                    "message": "Tenant not found"
                }
            )

        return tenant


async def validate_api_key_exists(
    tenant_id: UUID,
    api_key_id: UUID
) -> APIKey:
    """
    Validate API key exists and belongs to tenant

    Args:
        tenant_id: Tenant UUID
        api_key_id: API key UUID

    Returns:
        APIKey object

    Raises:
        HTTPException(404): If API key not found or doesn't belong to tenant
    """
    async with get_db_session() as session:
        stmt = select(APIKey).where(
            APIKey.id == api_key_id,
            APIKey.tenant_id == tenant_id
        )
        result = await session.execute(stmt)
        api_key = result.scalar_one_or_none()

        if not api_key:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "resource_not_found",
                    "message": "API key not found"
                }
            )

        return api_key


async def check_duplicate_email(email: str, exclude_tenant_id: Optional[UUID] = None) -> None:
    """
    Check if email is already used by another tenant

    Args:
        email: Email to check
        exclude_tenant_id: Tenant ID to exclude from check (for updates)

    Raises:
        HTTPException(409): If email already exists
    """
    async with get_db_session() as session:
        stmt = select(Tenant).where(
            Tenant.email == email,
            Tenant.deleted_at.is_(None)  # Not soft deleted
        )

        if exclude_tenant_id:
            stmt = stmt.where(Tenant.id != exclude_tenant_id)

        result = await session.execute(stmt)
        existing_tenant = result.scalar_one_or_none()

        if existing_tenant:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "duplicate_email",
                    "message": "A tenant with this email already exists",
                    "details": {"email": email}
                }
            )


async def check_api_key_quota(tenant_id: UUID) -> None:
    """
    Check if tenant has reached API key quota

    Quota (from TenantManager.PLAN_CONFIGS):
    - All plans: max 10 API keys

    Args:
        tenant_id: Tenant UUID

    Raises:
        HTTPException(422): If quota exceeded
    """
    async with get_db_session() as session:
        # Count active API keys
        from sqlalchemy import func
        stmt = select(func.count(APIKey.id)).where(
            APIKey.tenant_id == tenant_id,
            APIKey.is_active == True
        )
        result = await session.execute(stmt)
        count = result.scalar()

        max_keys = 10  # From TenantManager.PLAN_CONFIGS

        if count >= max_keys:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "quota_exceeded",
                    "message": f"Maximum API keys limit reached ({count}/{max_keys})",
                    "details": {
                        "current": count,
                        "max": max_keys
                    }
                }
            )


# ============================================================================
# ERROR HELPERS
# ============================================================================

def create_error_response(
    error_code: str,
    message: str,
    request_id: str,
    details: Optional[dict] = None
) -> dict:
    """
    Create consistent error response

    Expert approval (Marcus Rodriguez):
    "Consistent error structure across all endpoints"

    Args:
        error_code: Machine-readable error code
        message: Human-readable message
        request_id: Request ID for audit trail
        details: Optional additional details

    Returns:
        Error response dict
    """
    response = {
        "error": error_code,
        "message": message,
        "request_id": request_id
    }

    if details:
        response["details"] = details

    return response

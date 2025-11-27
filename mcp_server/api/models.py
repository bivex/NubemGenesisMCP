"""
Pydantic Models for Tenant API

Request and response models for tenant management endpoints.
Design approved by expert panel (see TENANT_API_EXPERT_DEBATE.md)

Experts:
- Elena Volkov (API Architect - Stripe)
- Raj Patel (CSO)
- Marcus Rodriguez (Backend - FastAPI)
- Dr. Priya Patel (Database - PostgreSQL)
- Alex Martinez (VP Product)

Unanimous approval: 5/5
"""

from datetime import datetime
from typing import Optional, Literal, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ============================================================================
# TENANT MODELS
# ============================================================================

class TenantCreate(BaseModel):
    """
    Request model for creating a new tenant

    Validation (Pydantic):
    - name: 1-255 characters
    - email: valid email format
    - plan: must be free/pro/enterprise
    - invite_code: optional (for instant activation)
    """
    name: str = Field(..., min_length=1, max_length=255, description="Tenant name")
    email: EmailStr = Field(..., description="Tenant email (must be unique)")
    plan: Literal['free', 'pro', 'enterprise'] = Field(default='free', description="Subscription plan")
    invite_code: Optional[str] = Field(None, max_length=50, description="Optional invite code for instant activation")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Acme Corporation",
                "email": "admin@acme.com",
                "plan": "pro",
                "invite_code": "WELCOME2025"
            }
        }


class TenantUpdate(BaseModel):
    """
    Request model for updating a tenant

    All fields optional (partial update)
    """
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Tenant name")
    plan: Optional[Literal['free', 'pro', 'enterprise']] = Field(None, description="Subscription plan")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Acme Corporation Ltd",
                "plan": "enterprise"
            }
        }


class TenantResponse(BaseModel):
    """
    Response model for tenant data

    Returns full tenant details (used in GET/POST/PUT responses)
    """
    id: UUID = Field(..., description="Tenant unique ID")
    name: str = Field(..., description="Tenant name")
    email: str = Field(..., description="Tenant email")
    plan: str = Field(..., description="Subscription plan")
    status: str = Field(..., description="Tenant status (active/suspended/pending_verification)")
    created_at: datetime = Field(..., description="Creation timestamp")
    max_requests_per_month: int = Field(..., description="Monthly request quota")
    gcp_project_id: Optional[str] = Field(None, description="GCP project ID (if provisioned)")
    k8s_namespace: Optional[str] = Field(None, description="Kubernetes namespace (if provisioned)")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Acme Corporation",
                "email": "admin@acme.com",
                "plan": "pro",
                "status": "active",
                "created_at": "2025-10-26T10:00:00Z",
                "max_requests_per_month": 10000,
                "gcp_project_id": "acme-corp-tenant-abc123",
                "k8s_namespace": "tenant-acme-abc123"
            }
        }


class TenantListResponse(BaseModel):
    """
    Response model for paginated tenant list

    Includes pagination metadata
    """
    data: List[TenantResponse] = Field(..., description="List of tenants")
    pagination: Dict[str, Any] = Field(..., description="Pagination metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "data": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "name": "Acme Corp",
                        "email": "admin@acme.com",
                        "plan": "pro",
                        "status": "active",
                        "created_at": "2025-10-26T10:00:00Z",
                        "max_requests_per_month": 10000
                    }
                ],
                "pagination": {
                    "page": 1,
                    "page_size": 50,
                    "total_items": 1234,
                    "total_pages": 25,
                    "has_next": True,
                    "has_prev": False
                }
            }
        }


# ============================================================================
# API KEY MODELS
# ============================================================================

class APIKeyCreate(BaseModel):
    """
    Request model for creating a new API key

    Validation:
    - role: must be admin/member
    - name: optional friendly name (max 100 chars)
    """
    role: Literal['admin', 'member'] = Field(default='member', description="API key role")
    name: Optional[str] = Field(None, max_length=100, description="Friendly name for API key")

    class Config:
        json_schema_extra = {
            "example": {
                "role": "admin",
                "name": "Production API Key"
            }
        }


class APIKeyUpdate(BaseModel):
    """
    Request model for updating an API key

    Currently only supports toggling active status
    """
    is_active: Optional[bool] = Field(None, description="Enable/disable API key")

    class Config:
        json_schema_extra = {
            "example": {
                "is_active": False
            }
        }


class APIKeyResponse(BaseModel):
    """
    Response model for API key data

    SECURITY: Does NOT include full API key
    Only returns key_prefix for identification

    Full API key is ONLY returned once, at creation time
    """
    id: UUID = Field(..., description="API key unique ID")
    key_prefix: str = Field(..., description="API key prefix (e.g., 'nsfc_abc')")
    role: str = Field(..., description="API key role (admin/member)")
    is_active: bool = Field(..., description="Whether API key is active")
    created_at: datetime = Field(..., description="Creation timestamp")
    last_used_at: Optional[datetime] = Field(None, description="Last usage timestamp")
    name: Optional[str] = Field(None, description="Friendly name")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "660e8400-e29b-41d4-a716-446655440001",
                "key_prefix": "nsfc_abc",
                "role": "admin",
                "is_active": True,
                "created_at": "2025-10-26T10:00:00Z",
                "last_used_at": "2025-10-26T15:30:00Z",
                "name": "Production API Key"
            }
        }


class APIKeyCreateResponse(APIKeyResponse):
    """
    Response model for API key creation

    SECURITY: Includes full API key ONLY on creation
    Warning message reminds user to save it

    Expert approval (Raj Patel, CSO):
    "Full API key is returned ONLY ONCE, at creation time. This is
    how GitHub, Stripe, AWS all work. Non-negotiable."
    """
    api_key: str = Field(..., description="Full API key (ONLY returned once)")
    warning: str = Field(
        default="Save this API key now. You won't be able to see it again.",
        description="Security warning"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": "660e8400-e29b-41d4-a716-446655440001",
                "api_key": "nsfc_abc123def456ghi789jkl012mno345pqr678stu",
                "key_prefix": "nsfc_abc",
                "role": "admin",
                "is_active": True,
                "created_at": "2025-10-26T10:00:00Z",
                "last_used_at": None,
                "name": "Production API Key",
                "warning": "Save this API key now. You won't be able to see it again."
            }
        }


class APIKeyListResponse(BaseModel):
    """
    Response model for paginated API key list

    Includes pagination metadata
    """
    data: List[APIKeyResponse] = Field(..., description="List of API keys")
    pagination: Dict[str, Any] = Field(..., description="Pagination metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "data": [
                    {
                        "id": "660e8400-e29b-41d4-a716-446655440001",
                        "key_prefix": "nsfc_abc",
                        "role": "admin",
                        "is_active": True,
                        "created_at": "2025-10-26T10:00:00Z",
                        "last_used_at": "2025-10-26T15:30:00Z",
                        "name": "Production API Key"
                    }
                ],
                "pagination": {
                    "page": 1,
                    "page_size": 50,
                    "total_items": 5,
                    "total_pages": 1,
                    "has_next": False,
                    "has_prev": False
                }
            }
        }


# ============================================================================
# USAGE & QUOTA MODELS
# ============================================================================

class UsageMetrics(BaseModel):
    """
    Usage metrics for a time period
    """
    requests: int = Field(..., description="Number of requests")
    tokens_input: int = Field(..., description="Input tokens used")
    tokens_output: int = Field(..., description="Output tokens used")
    tokens_total: int = Field(..., description="Total tokens used")

    class Config:
        json_schema_extra = {
            "example": {
                "requests": 1234,
                "tokens_input": 45678,
                "tokens_output": 23456,
                "tokens_total": 69134
            }
        }


class UsageResponse(BaseModel):
    """
    Response model for usage metrics

    Includes current month, last month, and total
    """
    tenant_id: UUID = Field(..., description="Tenant unique ID")
    current_month: UsageMetrics = Field(..., description="Current month usage")
    last_month: UsageMetrics = Field(..., description="Last month usage")
    total: UsageMetrics = Field(..., description="Total all-time usage")

    class Config:
        json_schema_extra = {
            "example": {
                "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                "current_month": {
                    "requests": 543,
                    "tokens_input": 12345,
                    "tokens_output": 6789,
                    "tokens_total": 19134
                },
                "last_month": {
                    "requests": 1234,
                    "tokens_input": 45678,
                    "tokens_output": 23456,
                    "tokens_total": 69134
                },
                "total": {
                    "requests": 5678,
                    "tokens_input": 123456,
                    "tokens_output": 67890,
                    "tokens_total": 191346
                }
            }
        }


class QuotaLimits(BaseModel):
    """
    Quota limits for a plan
    """
    max_requests_per_month: int = Field(..., description="Monthly request limit")
    max_api_keys: int = Field(..., description="Maximum API keys allowed")
    max_personas_active: int = Field(..., description="Maximum active personas")

    class Config:
        json_schema_extra = {
            "example": {
                "max_requests_per_month": 10000,
                "max_api_keys": 10,
                "max_personas_active": 25
            }
        }


class QuotaUsage(BaseModel):
    """
    Current quota usage
    """
    requests_this_month: int = Field(..., description="Requests used this month")
    api_keys_count: int = Field(..., description="Number of API keys")
    personas_active_count: int = Field(..., description="Number of active personas")

    class Config:
        json_schema_extra = {
            "example": {
                "requests_this_month": 543,
                "api_keys_count": 3,
                "personas_active_count": 12
            }
        }


class QuotaRemaining(BaseModel):
    """
    Remaining quota
    """
    requests: int = Field(..., description="Remaining requests this month")
    api_keys: int = Field(..., description="API keys that can still be created")
    personas_active: int = Field(..., description="Personas that can be activated")

    class Config:
        json_schema_extra = {
            "example": {
                "requests": 9457,
                "api_keys": 7,
                "personas_active": 13
            }
        }


class QuotaResponse(BaseModel):
    """
    Response model for quota status

    Includes limits, usage, remaining, and percentage
    """
    tenant_id: UUID = Field(..., description="Tenant unique ID")
    plan: str = Field(..., description="Subscription plan")
    limits: QuotaLimits = Field(..., description="Quota limits")
    usage: QuotaUsage = Field(..., description="Current usage")
    remaining: QuotaRemaining = Field(..., description="Remaining quota")
    percentage_used: float = Field(..., description="Percentage of quota used (0-100)")

    class Config:
        json_schema_extra = {
            "example": {
                "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                "plan": "pro",
                "limits": {
                    "max_requests_per_month": 10000,
                    "max_api_keys": 10,
                    "max_personas_active": 25
                },
                "usage": {
                    "requests_this_month": 543,
                    "api_keys_count": 3,
                    "personas_active_count": 12
                },
                "remaining": {
                    "requests": 9457,
                    "api_keys": 7,
                    "personas_active": 13
                },
                "percentage_used": 5.43
            }
        }


# ============================================================================
# ERROR MODELS
# ============================================================================

class ErrorResponse(BaseModel):
    """
    Standard error response

    Consistent structure across all endpoints
    Expert approval (Marcus Rodriguez):
    "Consistent error structure, appropriate HTTP status codes"
    """
    error: str = Field(..., description="Error code (machine-readable)")
    message: str = Field(..., description="Error message (human-readable)")
    request_id: str = Field(..., description="Request ID for audit trail")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "duplicate_email",
                "message": "A tenant with this email already exists",
                "request_id": "550e8400-e29b-41d4-a716-446655440000",
                "details": {
                    "email": "admin@acme.com"
                }
            }
        }


class ValidationErrorDetail(BaseModel):
    """
    Validation error detail
    """
    field: str = Field(..., description="Field name")
    message: str = Field(..., description="Validation error message")

    class Config:
        json_schema_extra = {
            "example": {
                "field": "email",
                "message": "value is not a valid email address"
            }
        }


class ValidationErrorResponse(ErrorResponse):
    """
    Validation error response (422)

    Includes list of field-level errors
    """
    details: Dict[str, List[ValidationErrorDetail]] = Field(
        ...,
        description="Validation errors by field"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "error": "validation_error",
                "message": "Input validation failed",
                "request_id": "550e8400-e29b-41d4-a716-446655440000",
                "details": {
                    "errors": [
                        {
                            "field": "email",
                            "message": "value is not a valid email address"
                        },
                        {
                            "field": "plan",
                            "message": "value must be one of: free, pro, enterprise"
                        }
                    ]
                }
            }
        }

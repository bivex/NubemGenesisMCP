"""
Middleware Package

Provides authentication, rate limiting, RLS, and audit logging middleware
for multi-tenant system.

Design approved by expert panel (see AUTH_MIDDLEWARE_EXPERT_DEBATE.md)

Middleware order (CRITICAL - approved by panel):
1. RequestIDMiddleware      # Generate request_id
2. PrometheusMiddleware      # Metrics
3. RateLimitMiddleware       # Check quota (before expensive auth)
4. AuthenticationMiddleware  # Validate API key
5. RLSMiddleware             # Set PostgreSQL context
6. [Application routes]
7. AuditLogMiddleware        # Log (async, non-blocking)
"""

from functools import wraps
from typing import Callable

from .auth import AuthenticationMiddleware
from .rls import RLSMiddleware, RLSContextManager


def public_endpoint(func: Callable) -> Callable:
    """
    Decorator to mark an endpoint as public (no authentication required)

    Usage:
        from mcp_server.middleware import public_endpoint

        @app.get("/health")
        @public_endpoint
        async def health():
            return {"status": "ok"}

    Note:
        The AuthenticationMiddleware checks for the _is_public attribute
        on the endpoint function. If present and True, authentication is skipped.

    Args:
        func: Endpoint function to decorate

    Returns:
        Decorated function with _is_public=True attribute
    """
    func._is_public = True
    return func


__all__ = [
    "AuthenticationMiddleware",
    "RLSMiddleware",
    "RLSContextManager",
    "public_endpoint"
]

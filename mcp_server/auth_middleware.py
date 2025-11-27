"""
Authentication and Authorization Middleware for MCP HTTP Server
Integrates with core/auth components
"""

import logging
import json
from typing import Dict, Optional, Callable
from aiohttp import web

# Import auth components
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.auth import get_auth_manager, get_audit_logger, get_rate_limiter, get_hybrid_auth_manager

logger = logging.getLogger(__name__)


# Public endpoints that don't require authentication
PUBLIC_ENDPOINTS = [
    '/health',
    '/metrics',  # Prometheus metrics if implemented
    '/auth/device/code',      # OAuth Device Flow: Request device code
    '/auth/device/token',     # OAuth Device Flow: Poll for token
    '/auth/device/verify',    # OAuth Device Flow: Verify user_code
    '/device',                # OAuth Device Flow: Device authorization page (HTML)
    '/auth/google',           # OAuth Web Flow: Google OAuth initiation
    '/auth/google/callback',  # OAuth Web Flow: Google OAuth callback
]


@web.middleware
async def auth_middleware(request: web.Request, handler: Callable) -> web.Response:
    """
    Authentication and Authorization Middleware.

    Validates API key, checks permissions, enforces rate limits, and audits all requests.

    Args:
        request: aiohttp request
        handler: Next handler in chain

    Returns:
        web.Response
    """
    # Skip authentication for public endpoints
    if request.path in PUBLIC_ENDPOINTS:
        return await handler(request)

    # Get managers
    auth_manager = get_auth_manager()
    audit_logger = get_audit_logger()
    rate_limiter = get_rate_limiter()
    hybrid_auth = get_hybrid_auth_manager()

    # Get client info
    client_ip = request.remote or "unknown"
    user_agent = request.headers.get('User-Agent', 'unknown')

    # Convert headers to dict for hybrid authentication
    headers_dict = {k: v for k, v in request.headers.items()}

    # Try hybrid authentication (API Key OR Bearer token)
    success, user, auth_type = await hybrid_auth.authenticate(headers_dict)

    # Get credential prefix for logging
    credential_prefix = "missing"
    if auth_type == "api_key":
        api_key = headers_dict.get('X-API-Key', '')
        credential_prefix = api_key[:15] + "..." if api_key else "missing"
    elif auth_type == "oauth":
        auth_header = headers_dict.get('Authorization', '')
        token = auth_header[7:] if auth_header.startswith('Bearer ') else ''
        credential_prefix = f"Bearer {token[:15]}..." if token else "missing"

    # Handle authentication failure
    if not success:
        if auth_type == "none":
            # No credentials provided
            audit_logger.log_auth_failed(
                api_key_prefix=credential_prefix,
                reason="No authentication credentials provided",
                ip_address=client_ip,
                user_agent=user_agent
            )

            return web.json_response(
                {
                    "error": "Authentication required",
                    "message": "Please provide authentication credentials",
                    "code": "MISSING_AUTH",
                    "supported_methods": ["X-API-Key header", "Authorization: Bearer token"],
                    "help": {
                        "api_key": "Include 'X-API-Key: your-key' header",
                        "oauth": "Run 'nubemsfc auth login' to get OAuth token"
                    }
                },
                status=401,
                headers={'WWW-Authenticate': 'X-API-Key, Bearer'}
            )

        elif auth_type == "invalid":
            # Invalid credentials
            audit_logger.log_auth_failed(
                api_key_prefix=credential_prefix,
                reason="Invalid authentication credentials",
                ip_address=client_ip,
                user_agent=user_agent
            )

            return web.json_response(
                {
                    "error": "Authentication failed",
                    "message": "Invalid authentication credentials",
                    "code": "INVALID_AUTH"
                },
                status=401,
                headers={'WWW-Authenticate': 'X-API-Key, Bearer'}
            )

    # Auth successful
    user_email = user.get('user_email')
    user_role = user.get('role')

    audit_logger.log_auth_success(
        user_email=user_email,
        user_role=user_role,
        api_key_prefix=credential_prefix,
        ip_address=client_ip,
        user_agent=user_agent
    )

    # Log authentication type for audit purposes
    logger.info(f"Authentication successful: user={user_email}, type={auth_type}, ip={client_ip}")

    # Check rate limit (use hybrid auth for consistent handling)
    rate_limits = hybrid_auth.get_user_rate_limit(user)
    allowed, rate_info = rate_limiter.check_rate_limit(
        user_email=user_email,
        requests_per_minute=rate_limits["requests_per_minute"],
        burst=rate_limits["burst"]
    )

    if not allowed:
        audit_logger.log_rate_limit_exceeded(
            user_email=user_email,
            user_role=user_role,
            api_key_prefix=credential_prefix,
            ip_address=client_ip
        )

        return web.json_response(
            {
                "error": "Rate limit exceeded",
                "message": f"Too many requests. Limit: {rate_info['limit']}/min",
                "code": "RATE_LIMIT_EXCEEDED",
                "rate_limit": rate_info
            },
            status=429,
            headers={
                'X-RateLimit-Limit': str(rate_info['limit']),
                'X-RateLimit-Remaining': str(max(0, rate_info['limit'] - rate_info['current_count'])),
                'X-RateLimit-Reset': str(rate_info['reset_in_seconds'])
            }
        )

    # Extract tool/MCP from request body (for permission check)
    tool_name = None
    mcp_name = None

    try:
        if request.can_read_body:
            body = await request.json()

            # Extract tool name from MCP request
            if isinstance(body, dict):
                # MCP JSON-RPC format
                if body.get('method') == 'tools/call':
                    params = body.get('params', {})
                    tool_name = params.get('name')

                    # Try to detect MCP usage from tool arguments
                    # (This is heuristic - some tools use MCPs internally)
                    args = params.get('arguments', {})
                    if 'mcp_name' in args:
                        mcp_name = args['mcp_name']

                elif body.get('method') == 'tools/list':
                    tool_name = 'tools/list'

                # Direct tool call format
                elif 'name' in body:
                    tool_name = body.get('name')

    except Exception as e:
        logger.warning(f"Could not extract tool name from request: {e}")
        tool_name = "unknown"

    # Default operation is read (most tools are read operations)
    operation = "read"

    # Certain tools/MCPs are write operations
    WRITE_OPERATIONS = [
        'intelligent_execute',  # Can execute MCPs that modify infrastructure
        'orchestrate'
    ]

    if tool_name in WRITE_OPERATIONS or (mcp_name and mcp_name in ['kubernetes', 'docker', 'gcp', 'github', 'filesystem']):
        operation = "write"

    # Check permission (use hybrid auth for consistent handling)
    # For tools that don't directly use MCPs, use tool name as permission check
    permission_target = mcp_name if mcp_name else (tool_name if tool_name else "unknown")

    # Skip permission check for certain metadata/introspection methods
    SKIP_PERMISSION_CHECK = ['tools/list', 'tools/schema', 'unknown']

    if permission_target and permission_target not in SKIP_PERMISSION_CHECK:
        has_permission = hybrid_auth.check_permission(
            user=user,
            mcp_name=permission_target,
            operation=operation
        )

        if not has_permission:
            audit_logger.log_permission_check(
                user_email=user_email,
                user_role=user_role,
                tool_name=tool_name or "unknown",
                mcp_name=mcp_name,
                operation=operation,
                allowed=False,
                reason=f"User role '{user_role}' not authorized for '{permission_target}'"
            )

            return web.json_response(
                {
                    "error": "Permission denied",
                    "message": f"User role '{user_role}' is not authorized to access '{permission_target}'",
                    "code": "PERMISSION_DENIED",
                    "user_role": user_role,
                    "required_permission": permission_target
                },
                status=403
            )

        # Log permission granted
        audit_logger.log_permission_check(
            user_email=user_email,
            user_role=user_role,
            tool_name=tool_name or "unknown",
            mcp_name=mcp_name,
            operation=operation,
            allowed=True
        )

    # Attach user info to request for downstream handlers (optional)
    request['user'] = user
    request['user_email'] = user_email
    request['user_role'] = user_role

    # Execute request
    try:
        import time
        start_time = time.time()

        response = await handler(request)

        execution_time_ms = (time.time() - start_time) * 1000

        # Log successful tool invocation
        audit_logger.log_tool_invocation(
            user_email=user_email,
            user_role=user_role,
            tool_name=tool_name or "unknown",
            mcp_name=mcp_name,
            operation=operation,
            status="success",
            execution_time_ms=execution_time_ms
        )

        # Add custom headers to response
        response.headers['X-User-Role'] = user_role
        response.headers['X-RateLimit-Remaining'] = str(max(0, rate_info['limit'] - rate_info['current_count']))

        return response

    except Exception as e:
        # Log failed tool invocation
        audit_logger.log_tool_invocation(
            user_email=user_email,
            user_role=user_role,
            tool_name=tool_name or "unknown",
            mcp_name=mcp_name,
            operation=operation,
            status="error",
            error=str(e)
        )

        raise  # Re-raise to let aiohttp handle it


def setup_auth_middleware(app: web.Application):
    """
    Setup authentication middleware on aiohttp application.

    Args:
        app: aiohttp Application

    Usage:
        app = web.Application()
        setup_auth_middleware(app)
    """
    app.middlewares.append(auth_middleware)
    logger.info("✅ Authentication middleware enabled")

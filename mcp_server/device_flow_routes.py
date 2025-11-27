"""
OAuth 2.0 Device Flow Routes (RFC 8628)

Implements device authorization grant for CLI and limited-input devices.
Design approved by expert panel (see OAUTH_DEVICE_FLOW_DESIGN.md)

Endpoints:
- POST /auth/device/code - Request device and user codes
- POST /auth/device/token - Poll for authorization token
- POST /auth/device/verify - Verify user code and initiate OAuth
- GET /device - Device authorization page (HTML)

Flow:
1. CLI requests device code → POST /auth/device/code
2. CLI displays user_code and verification URI
3. User visits /device in browser
4. User enters user_code → POST /auth/device/verify
5. Redirect to Google OAuth
6. After OAuth success, device is approved
7. CLI polls → POST /auth/device/token → receives JWT token
"""

import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Request, Response, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from core.auth.device_flow_handler import DeviceFlowOAuthHandler
from core.auth.oauth_handler import get_oauth_handler, GoogleOAuthHandler
from core.auth.device_code_storage import DeviceCodeStorage
from core.auth.rate_limiter import RateLimiter
from core.auth.audit_logger import AuditLogger
from core.cache import TwoTierCache
from mcp_server.middleware import public_endpoint

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/auth/device", tags=["Device Flow"])

# Templates (will be initialized in startup)
templates: Optional[Jinja2Templates] = None

# Device flow handler (will be initialized)
device_flow_handler: Optional[DeviceFlowOAuthHandler] = None


def init_device_flow_routes(
    cache_instance: TwoTierCache,
    templates_instance: Jinja2Templates,
    device_handler: DeviceFlowOAuthHandler
):
    """
    Initialize device flow routes with dependencies.

    Args:
        cache_instance: TwoTierCache instance
        templates_instance: Jinja2Templates instance
        device_handler: DeviceFlowOAuthHandler instance
    """
    global cache, templates, device_flow_handler
    cache = cache_instance
    templates = templates_instance
    device_flow_handler = device_handler
    logger.info("✅ Device flow routes initialized")


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class DeviceCodeRequest(BaseModel):
    """Request body for POST /auth/device/code"""
    client_id: str = Field(..., description="OAuth client ID (e.g., 'nubemsfc-cli')")
    scope: str = Field(default="openid email profile", description="Requested OAuth scopes")


class DeviceCodeResponse(BaseModel):
    """Response for POST /auth/device/code"""
    device_code: str = Field(..., description="Device code for polling")
    user_code: str = Field(..., description="User code to display (XXXX-XXXX)")
    verification_uri: str = Field(..., description="URL for user to visit")
    verification_uri_complete: str = Field(..., description="URL with pre-filled user_code")
    expires_in: int = Field(..., description="Seconds until expiration (900)")
    interval: int = Field(..., description="Minimum polling interval in seconds (5)")


class DeviceTokenRequest(BaseModel):
    """Request body for POST /auth/device/token"""
    grant_type: str = Field(..., description="Must be 'urn:ietf:params:oauth:grant-type:device_code'")
    device_code: str = Field(..., description="Device code from /auth/device/code")
    client_id: str = Field(..., description="OAuth client ID")


class DeviceTokenResponse(BaseModel):
    """Response for POST /auth/device/token (success)"""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="Bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiry in seconds (86400)")
    scope: str = Field(..., description="Granted scopes")


class DeviceTokenErrorResponse(BaseModel):
    """Error response for POST /auth/device/token"""
    error: str = Field(..., description="Error code (authorization_pending, slow_down, expired_token, access_denied)")
    error_description: str = Field(..., description="Human-readable error description")


class DeviceVerifyRequest(BaseModel):
    """Request body for POST /auth/device/verify"""
    user_code: str = Field(..., description="User code (XXXX-XXXX format)")


class DeviceVerifyResponse(BaseModel):
    """Response for POST /auth/device/verify"""
    authorization_url: str = Field(..., description="Google OAuth URL to redirect to")


# ============================================================================
# ENDPOINT 1: POST /auth/device/code - Request Device Code
# ============================================================================

@router.post("/code", response_model=DeviceCodeResponse)
@public_endpoint
async def request_device_code(
    request: Request,
    body: DeviceCodeRequest
) -> DeviceCodeResponse:
    """
    Initiate device authorization flow.

    The CLI calls this endpoint to obtain a device_code and user_code.
    The CLI then displays the user_code and verification URI to the user.

    Security:
    - Rate limited: 10 requests per IP per hour
    - Device codes expire in 15 minutes
    - All operations are audit logged

    Args:
        request: FastAPI request object
        body: DeviceCodeRequest with client_id and scope

    Returns:
        DeviceCodeResponse with codes and URIs

    Raises:
        HTTPException 429: Rate limit exceeded
        HTTPException 500: Internal server error
    """
    if device_flow_handler is None:
        raise HTTPException(status_code=500, detail="Device flow not initialized")

    # Get client info
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent")

    try:
        # Generate device code
        result = await device_flow_handler.generate_device_code(
            client_id=body.client_id,
            scope=body.scope,
            client_ip=client_ip,
            user_agent=user_agent
        )

        logger.info(f"Device code generated: user_code={result['user_code']}, client_ip={client_ip}")

        return DeviceCodeResponse(**result)

    except ValueError as e:
        # Rate limit exceeded
        logger.warning(f"Device code request failed: {e}")
        raise HTTPException(
            status_code=429,
            detail={
                "error": "slow_down",
                "error_description": str(e)
            }
        )
    except Exception as e:
        logger.error(f"Error generating device code: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "server_error",
                "error_description": "Internal server error"
            }
        )


# ============================================================================
# ENDPOINT 2: POST /auth/device/token - Poll for Token
# ============================================================================

@router.post("/token")
@public_endpoint
async def poll_device_token(
    request: Request,
    body: DeviceTokenRequest
) -> JSONResponse:
    """
    Poll for device authorization status and retrieve token.

    The CLI calls this endpoint repeatedly (every 5+ seconds) until:
    - User completes authorization → returns JWT token
    - User denies authorization → returns access_denied error
    - Device code expires → returns expired_token error

    Security:
    - Enforces minimum 5-second polling interval (slow_down response)
    - Single-use device codes (deleted after token issued)
    - All operations are audit logged

    Args:
        request: FastAPI request object
        body: DeviceTokenRequest with grant_type, device_code, client_id

    Returns:
        On success (200): DeviceTokenResponse with JWT token
        On pending (400): DeviceTokenErrorResponse with authorization_pending
        On too fast (400): DeviceTokenErrorResponse with slow_down
        On expired (400): DeviceTokenErrorResponse with expired_token
        On denied (400): DeviceTokenErrorResponse with access_denied

    Raises:
        HTTPException 400: Invalid grant type
        HTTPException 500: Internal server error
    """
    if device_flow_handler is None:
        raise HTTPException(status_code=500, detail="Device flow not initialized")

    # Validate grant type
    if body.grant_type != "urn:ietf:params:oauth:grant-type:device_code":
        return JSONResponse(
            status_code=400,
            content={
                "error": "unsupported_grant_type",
                "error_description": "Only device_code grant type is supported"
            }
        )

    try:
        # Poll for token
        result = await device_flow_handler.poll_for_token(
            device_code=body.device_code,
            client_id=body.client_id
        )

        # Check if error response
        if "error" in result:
            error_code = result["error"]

            # Log different error types
            if error_code == "authorization_pending":
                # Normal polling state, don't log as error
                pass
            elif error_code == "slow_down":
                logger.debug(f"Device polling too fast: {body.device_code[:15]}...")
            else:
                logger.info(f"Device token poll error: {error_code}, device={body.device_code[:15]}...")

            return JSONResponse(status_code=400, content=result)

        # Success - return token
        logger.info(f"Device token issued: device={body.device_code[:15]}...")
        return JSONResponse(status_code=200, content=result)

    except Exception as e:
        logger.error(f"Error polling device token: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "server_error",
                "error_description": "Internal server error"
            }
        )


# ============================================================================
# ENDPOINT 3: POST /auth/device/verify - Verify User Code
# ============================================================================

@router.post("/verify", response_model=DeviceVerifyResponse)
@public_endpoint
async def verify_user_code(
    request: Request,
    body: DeviceVerifyRequest
) -> DeviceVerifyResponse:
    """
    Verify user code and initiate Google OAuth flow.

    Called by the device authorization page after user enters the user_code.
    Validates the code and returns a Google OAuth URL to redirect to.

    After successful OAuth, the device will be approved and the CLI can
    retrieve the token.

    Security:
    - User code validated before OAuth redirect
    - OAuth state linked to device code
    - All operations are audit logged

    Args:
        request: FastAPI request object
        body: DeviceVerifyRequest with user_code

    Returns:
        DeviceVerifyResponse with authorization_url

    Raises:
        HTTPException 400: Invalid or expired user code
        HTTPException 500: Internal server error
    """
    if device_flow_handler is None:
        raise HTTPException(status_code=500, detail="Device flow not initialized")

    # Normalize user code
    user_code = body.user_code.upper().strip()

    try:
        # Verify user code exists
        device_code = await device_flow_handler.verify_user_code(user_code)

        if device_code is None:
            logger.warning(f"Invalid user code: {user_code}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_code",
                    "error_description": "Invalid or expired user code"
                }
            )

        # Get OAuth handler
        oauth_handler = get_oauth_handler()

        if not oauth_handler.is_configured():
            logger.error("OAuth not configured")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "server_error",
                    "error_description": "OAuth not configured"
                }
            )

        # Generate OAuth URL
        oauth_data = oauth_handler.get_authorization_url()

        # Store OAuth state -> device_code mapping
        # This allows the OAuth callback to find the device that initiated the flow
        await device_flow_handler.storage.store_oauth_state(
            state=oauth_data["state"],
            device_code=device_code,
            ttl=900  # 15 minutes
        )

        # Also store OAuth session data (state, nonce, code_verifier) in cache
        # for the OAuth callback handler to validate
        if cache:
            session_key = f"oauth_session:{oauth_data['state']}"
            session_data = {
                "state": oauth_data["state"],
                "nonce": oauth_data["nonce"],
                "code_verifier": oauth_data["code_verifier"],
                "device_flow": True,  # Marker for device flow
                "user_code": user_code,
                "device_code": device_code,
                "created_at": datetime.utcnow().isoformat()
            }
            await cache.set(session_key, session_data, ttl=600)

        logger.info(f"User code verified: {user_code} -> device {device_code[:15]}...")

        return DeviceVerifyResponse(authorization_url=oauth_data["authorization_url"])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying user code: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "server_error",
                "error_description": "Internal server error"
            }
        )


# ============================================================================
# ENDPOINT 4: GET /device - Device Authorization Page
# ============================================================================

# Note: This route is registered at the root level (not under /auth/device)
# It's added here for documentation but needs to be registered separately

def create_device_page_route():
    """
    Create the GET /device route for device authorization page.

    This is a separate function because it needs to be registered
    at the root router level (not under /auth/device prefix).

    Returns:
        FastAPI route handler
    """
    async def device_authorization_page(request: Request, user_code: Optional[str] = None):
        """
        Render device authorization page.

        User visits this page to enter the user_code displayed by the CLI.
        The page can optionally pre-fill the user_code from query params.

        Args:
            request: FastAPI request object
            user_code: Optional pre-filled user code from query param

        Returns:
            HTMLResponse with device authorization page
        """
        if templates is None:
            return HTMLResponse(
                content="<html><body><h1>Error: Templates not initialized</h1></body></html>",
                status_code=500
            )

        return templates.TemplateResponse(
            "device_authorization.html",
            {
                "request": request,
                "user_code": user_code or "",
                "verification_uri": "/auth/device/verify"
            }
        )

    return device_authorization_page

"""
OAuth Authentication Routes

Implements Google OAuth 2.0 flow with automatic tenant provisioning.
Design approved by 6 L5 expert panel (see OAUTH_TENANT_INTEGRATION_EXPERT_DEBATE.md)

Endpoints:
- GET /auth/google/login - Initiate OAuth flow
- GET /auth/google/callback - Handle OAuth callback from Google
- GET /dashboard - User dashboard (authenticated)
- GET /login - Login page
- POST /auth/logout - Logout

Flow:
1. User clicks "Login with Google" → /auth/google/login
2. Redirect to Google OAuth
3. User authorizes
4. Google redirects back → /auth/google/callback
5. Create/get tenant automatically
6. Generate session token
7. Redirect to /dashboard with API key (if new tenant)
"""

import logging
import secrets
from typing import Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Request, Response, HTTPException, Cookie, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from core.auth.oauth_handler import get_oauth_handler, GoogleOAuthHandler
from core.tenant_provisioning import (
    create_or_get_tenant_atomic,
    get_tenant_by_id,
    is_email_allowed
)
from core.rate_limiting import check_tenant_creation_rate_limit
from core.cache import TwoTierCache
from mcp_server.middleware import public_endpoint

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/auth", tags=["Authentication"])

# Templates (will be initialized in startup)
templates: Optional[Jinja2Templates] = None

# Cache (will be injected)
cache: Optional[TwoTierCache] = None


def init_auth_routes(cache_instance: TwoTierCache, templates_instance: Jinja2Templates):
    """
    Initialize auth routes with dependencies.

    Args:
        cache_instance: TwoTierCache instance
        templates_instance: Jinja2Templates instance
    """
    global cache, templates
    cache = cache_instance
    templates = templates_instance
    logger.info("✅ Auth routes initialized")


# ============================================================================
# OAUTH FLOW - STEP 1: Initiate OAuth
# ============================================================================

@router.get("/google/login")
@public_endpoint
async def google_login(request: Request, response: Response):
    """
    Initiate Google OAuth 2.0 flow.

    Flow:
    1. Generate authorization URL with state/nonce/PKCE
    2. Store OAuth session in cache (state, nonce, code_verifier)
    3. Set session cookie
    4. Redirect user to Google OAuth consent screen

    Returns:
        Redirect 302 to Google OAuth authorization URL

    Security (Dr. Elena Volkov):
    - State parameter for CSRF protection
    - Nonce for replay attack prevention
    - PKCE (code_challenge) for authorization code interception prevention
    - OAuth session stored in Redis (10 min expiry)
    """
    oauth_handler = get_oauth_handler()

    if not oauth_handler.is_configured():
        logger.error("OAuth not configured")
        return HTMLResponse(
            content="""
            <html>
                <body>
                    <h1>OAuth Not Configured</h1>
                    <p>Google OAuth is not configured on this server.</p>
                    <p>Please contact the administrator.</p>
                </body>
            </html>
            """,
            status_code=503
        )

    try:
        # Generate OAuth authorization URL
        auth_data = oauth_handler.get_authorization_url()

        # Store OAuth session in cache (Redis)
        session_id = secrets.token_urlsafe(32)
        session_key = f'oauth_session:{session_id}'

        await cache.set(
            session_key,
            {
                'state': auth_data['state'],
                'nonce': auth_data['nonce'],
                'code_verifier': auth_data['code_verifier'],
                'created_at': str(datetime.utcnow())
            },
            ttl=600  # 10 minutes
        )

        logger.info(f"OAuth session created: {session_id}")

        # Redirect to Google OAuth
        redirect_response = RedirectResponse(
            url=auth_data['authorization_url'],
            status_code=302
        )

        # Set session cookie
        redirect_response.set_cookie(
            key='oauth_session_id',
            value=session_id,
            max_age=600,  # 10 minutes
            httponly=True,
            secure=True,  # HTTPS only
            samesite='lax'  # Allow redirect from Google
        )

        return redirect_response

    except Exception as e:
        logger.error(f"Error initiating OAuth: {e}", exc_info=True)
        raise HTTPException(500, "Failed to initiate OAuth flow")


# ============================================================================
# OAUTH FLOW - STEP 2: Handle Callback
# ============================================================================

@router.get("/google/callback")
@public_endpoint
async def google_callback(
    request: Request,
    code: str,
    state: str,
    oauth_session_id: Optional[str] = Cookie(None)
):
    """
    Handle OAuth callback from Google.

    Flow:
    1. Validate state (CSRF protection)
    2. Exchange authorization code for tokens (with PKCE)
    3. Validate ID token
    4. Check email verification
    5. Check rate limits
    6. Create or get tenant (atomic)
    7. Generate session token
    8. Redirect to dashboard

    Args:
        code: Authorization code from Google
        state: State parameter from Google (CSRF protection)
        oauth_session_id: OAuth session ID from cookie

    Returns:
        Redirect to /dashboard with session cookie

    Raises:
        HTTPException 400: Missing session or invalid state
        HTTPException 403: Email not verified or not authorized
        HTTPException 429: Rate limit exceeded
    """
    oauth_handler = get_oauth_handler()

    try:
        # Step 1: Get OAuth session
        if not oauth_session_id:
            logger.error("Missing oauth_session_id cookie")
            return await render_error(
                request,
                "Missing Session",
                "OAuth session not found. Please try logging in again.",
                "/auth/google/login"
            )

        session_key = f'oauth_session:{oauth_session_id}'
        session_data = await cache.get(session_key)

        if not session_data:
            logger.error(f"OAuth session expired or not found: {oauth_session_id}")
            return await render_error(
                request,
                "Session Expired",
                "Your OAuth session has expired. Please try logging in again.",
                "/auth/google/login"
            )

        # Step 2: Validate state (CSRF protection)
        if state != session_data['state']:
            logger.error(f"State mismatch: {state} != {session_data['state']}")
            return await render_error(
                request,
                "Security Error",
                "Invalid state parameter (CSRF detected). Please try again.",
                "/auth/google/login"
            )

        # Step 3: Exchange code for tokens
        try:
            user_info = oauth_handler.exchange_code_for_tokens(
                code=code,
                code_verifier=session_data['code_verifier'],
                state=state,
                expected_state=session_data['state']
            )
        except Exception as e:
            logger.error(f"Failed to exchange code for tokens: {e}")
            return await render_error(
                request,
                "OAuth Error",
                f"Failed to authenticate with Google: {str(e)}",
                "/auth/google/login"
            )

        # Step 4: Security check - Email must be verified
        if not user_info.get('email_verified'):
            logger.warning(f"Email not verified: {user_info.get('email')}")
            return await render_error(
                request,
                "Email Not Verified",
                "Your email is not verified with Google. Please verify your email and try again.",
                "/auth/google/login",
                details="Go to https://myaccount.google.com to verify your email."
            )

        email = user_info['email']

        # Step 5: Check if email domain is allowed
        if not is_email_allowed(email):
            logger.warning(f"Email domain not authorized: {email}")
            return await render_error(
                request,
                "Unauthorized Email",
                f"Email domain not authorized: {email}",
                "/auth/google/login",
                details="Only specific email domains are allowed. Contact support for access."
            )

        # Step 6: Rate limiting
        client_ip = request.client.host
        allowed, reason = await check_tenant_creation_rate_limit(cache, client_ip, email)

        if not allowed:
            logger.warning(f"Rate limit exceeded for {email} from {client_ip}: {reason}")
            return await render_error(
                request,
                "Rate Limit Exceeded",
                reason,
                "/auth/google/login"
            )

        # Step 7: Create or get tenant (ATOMIC)
        try:
            tenant, api_key, is_new = await create_or_get_tenant_atomic(user_info)

            logger.info(f"✅ OAuth successful for {email}")
            logger.info(f"   - Tenant: {tenant.id} (new={is_new})")
            logger.info(f"   - Plan: {tenant.plan}")

        except Exception as e:
            logger.error(f"Failed to create/get tenant: {e}", exc_info=True)
            return await render_error(
                request,
                "Server Error",
                "Failed to create your account. Please try again later.",
                "/auth/google/login"
            )

        # Step 8: Generate session token
        session_token = oauth_handler.create_session_token(
            user_info={
                **user_info,
                'tenant_id': str(tenant.id),
                'role': 'admin'  # First user is admin
            },
            expires_in_hours=24
        )

        # Step 9: Clean up OAuth session
        await cache.delete(session_key)

        # Step 10: Redirect to dashboard
        redirect_response = RedirectResponse(
            url='/dashboard',
            status_code=302
        )

        # Set session cookie (24 hours)
        redirect_response.set_cookie(
            key='session_token',
            value=session_token,
            max_age=86400,  # 24 hours
            httponly=True,
            secure=True,  # HTTPS only
            samesite='strict'  # Strict for session
        )

        # If new tenant, set one-time API key cookie (for display)
        if is_new and api_key:
            redirect_response.set_cookie(
                key='new_api_key',
                value=api_key,
                max_age=60,  # 1 minute (read once, then deleted)
                httponly=False,  # JavaScript needs to read it
                secure=True,
                samesite='strict'
            )

        # Delete OAuth session cookie
        redirect_response.delete_cookie('oauth_session_id')

        return redirect_response

    except Exception as e:
        logger.error(f"Unexpected error in OAuth callback: {e}", exc_info=True)
        return await render_error(
            request,
            "Server Error",
            "An unexpected error occurred. Please try again.",
            "/auth/google/login"
        )


# ============================================================================
# DASHBOARD
# ============================================================================

@router.get("/dashboard", response_class=HTMLResponse)
@public_endpoint  # Will check session manually
async def dashboard(
    request: Request,
    session_token: Optional[str] = Cookie(None),
    new_api_key: Optional[str] = Cookie(None)
):
    """
    User dashboard (requires session token).

    Shows:
    - Welcome message
    - API key (if just created - one-time display)
    - Tenant info (plan, status)
    - Usage stats (requests, tokens)
    - Quota status (remaining)
    - Quick start guide

    Args:
        session_token: JWT session token (from cookie)
        new_api_key: One-time API key (if just created)

    Returns:
        HTML dashboard page
    """
    # Check session token
    if not session_token:
        # Not authenticated - redirect to login
        return RedirectResponse('/login', status_code=302)

    oauth_handler = get_oauth_handler()

    # Validate session token
    payload = oauth_handler.validate_session_token(session_token)

    if not payload:
        # Invalid or expired session - redirect to login
        logger.warning("Invalid or expired session token")
        response = RedirectResponse('/login', status_code=302)
        response.delete_cookie('session_token')
        return response

    try:
        # Get tenant
        tenant_id = UUID(payload['tenant_id'])
        tenant = await get_tenant_by_id(tenant_id)

        if not tenant:
            logger.error(f"Tenant not found: {tenant_id}")
            return await render_error(
                request,
                "Tenant Not Found",
                "Your account was not found. Please contact support.",
                "/login"
            )

        # Get usage and quota (placeholder - implement with actual queries)
        usage = {
            'requests': 0,
            'tokens_input': 0,
            'tokens_output': 0
        }

        quota = {
            'max_requests_per_month': tenant.max_requests_per_month,
            'remaining': tenant.max_requests_per_month - usage['requests']
        }

        # Render dashboard
        return templates.TemplateResponse('oauth_dashboard.html', {
            'request': request,
            'user_name': payload.get('name', payload.get('email')),
            'user_email': payload.get('email'),
            'tenant': tenant,
            'usage': usage,
            'quota': quota,
            'new_api_key': new_api_key,  # Will be None after first load
            'is_new_tenant': new_api_key is not None
        })

    except Exception as e:
        logger.error(f"Error rendering dashboard: {e}", exc_info=True)
        return await render_error(
            request,
            "Server Error",
            "Failed to load dashboard. Please try again.",
            "/login"
        )


# ============================================================================
# LOGIN PAGE
# ============================================================================

@router.get("/login", response_class=HTMLResponse)
@public_endpoint
async def login_page(request: Request):
    """
    Login page with "Sign in with Google" button.

    Returns:
        HTML login page
    """
    return templates.TemplateResponse('oauth_login.html', {
        'request': request
    })


# ============================================================================
# LOGOUT
# ============================================================================

@router.post("/logout")
@public_endpoint
async def logout(response: Response):
    """
    Logout user (delete session cookie).

    Returns:
        Redirect to login page
    """
    redirect_response = RedirectResponse('/login', status_code=302)
    redirect_response.delete_cookie('session_token')
    redirect_response.delete_cookie('new_api_key')

    return redirect_response


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def render_error(
    request: Request,
    title: str,
    message: str,
    retry_url: str,
    details: Optional[str] = None
) -> HTMLResponse:
    """
    Render error page.

    Args:
        request: Request object
        title: Error title
        message: Error message
        retry_url: URL to retry (e.g., /auth/google/login)
        details: Optional additional details

    Returns:
        HTML error page
    """
    return templates.TemplateResponse('oauth_error.html', {
        'request': request,
        'error_title': title,
        'error_message': message,
        'error_details': details,
        'retry_url': retry_url
    })

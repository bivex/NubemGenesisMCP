#!/usr/bin/env python3
"""
Secrets UI Routes for aiohttp integration
Full implementation with Google OAuth2 and complete CRUD operations
"""

import os
import logging
import json
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path
import secrets as python_secrets

from aiohttp import web, ClientSession
import aiohttp_jinja2
import jinja2
from jose import JWTError, jwt

# Import SecretsManager
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.secrets_manager import SecretsManager

logger = logging.getLogger(__name__)

# Configuration
SECRET_KEY = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 hours
ALLOWED_DOMAIN = os.getenv("ALLOWED_EMAIL_DOMAIN", "nubemsystems.es")

# Google OAuth2 Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8080/auth/google/callback")

# OAuth2 URLs
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# Initialize SecretsManager
secrets_manager = SecretsManager()


class SecretsUIRoutes:
    """
    Secrets UI routes adapter for aiohttp with Google OAuth2
    """

    def __init__(self, app: web.Application):
        self.app = app
        self._setup_templates()
        self._setup_routes()

    def _setup_templates(self):
        """Setup Jinja2 templates"""
        template_dir = Path(__file__).parent.parent / "templates"
        aiohttp_jinja2.setup(
            self.app,
            loader=jinja2.FileSystemLoader(str(template_dir))
        )
        logger.info(f"Templates directory: {template_dir}")

    def _setup_routes(self):
        """Setup Secrets UI routes"""
        # OAuth2 endpoints
        self.app.router.add_get('/auth/google', self.google_auth_init)
        self.app.router.add_get('/auth/google/callback', self.google_auth_callback)
        self.app.router.add_post('/auth/logout', self.logout)

        # API endpoints
        self.app.router.add_get('/api/v1/secrets', self.list_secrets)
        self.app.router.add_get('/api/v1/secrets/{secret_name}', self.get_secret)
        self.app.router.add_post('/api/v1/secrets', self.create_secret)
        self.app.router.add_put('/api/v1/secrets/{secret_name}', self.update_secret)
        self.app.router.add_delete('/api/v1/secrets/{secret_name}', self.delete_secret)
        self.app.router.add_get('/api/v1/me', self.get_current_user_info)

        # UI endpoints
        self.app.router.add_get('/secrets', self.secrets_dashboard)
        self.app.router.add_get('/secrets/dashboard', self.secrets_dashboard)
        self.app.router.add_get('/secrets/login', self.login_page)

        # Static files
        static_dir = Path(__file__).parent.parent / "static"
        if static_dir.exists():
            self.app.router.add_static('/static', path=str(static_dir), name='static')
            logger.info(f"Static files directory: {static_dir}")

        logger.info("✅ Secrets UI routes configured with Google OAuth2")

    # ==================== Authentication Helpers ====================

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    async def get_current_user(self, request: web.Request) -> Optional[Dict[str, Any]]:
        """
        Get current user from JWT token in Authorization header
        Returns None if no token or invalid
        """
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return None

        token = auth_header.replace('Bearer ', '')

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            email: str = payload.get("sub")
            if email is None:
                return None

            # Verify domain restriction
            if not email.endswith(f"@{ALLOWED_DOMAIN}"):
                logger.warning(f"User {email} not from allowed domain {ALLOWED_DOMAIN}")
                return None

            return {
                "email": email,
                "name": payload.get("name"),
                "picture": payload.get("picture")
            }
        except JWTError as e:
            logger.warning(f"JWT validation error: {e}")
            return None

    async def require_user(self, request: web.Request) -> Dict[str, Any]:
        """Require authenticated user, raise 401 if not"""
        user = await self.get_current_user(request)
        if user is None:
            raise web.HTTPUnauthorized(
                text=json.dumps({"detail": "Authentication required"}),
                content_type='application/json'
            )
        return user

    # ==================== OAuth2 Endpoints ====================

    async def google_auth_init(self, request: web.Request):
        """Initiate Google OAuth2 flow"""
        if not GOOGLE_CLIENT_ID:
            return web.json_response(
                {"error": "Google OAuth not configured"},
                status=500
            )

        # Generate state for CSRF protection
        state = python_secrets.token_urlsafe(32)

        # Store state in session (you might want to use a proper session store)
        # For now, we'll include it in the redirect and verify on callback

        params = {
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "hd": ALLOWED_DOMAIN,  # Restrict to domain
            "access_type": "online",
            "prompt": "select_account"
        }

        auth_url = f"{GOOGLE_AUTH_URL}?{'&'.join(f'{k}={v}' for k, v in params.items())}"

        return web.HTTPFound(auth_url)

    async def google_auth_callback(self, request: web.Request):
        """Handle Google OAuth2 callback - supports both Secrets UI and Device Flow"""
        code = request.query.get('code')
        state = request.query.get('state')
        error = request.query.get('error')

        if error:
            logger.error(f"OAuth error: {error}")
            return web.Response(
                text=f"<html><body><h1>Login Failed</h1><p>Error: {error}</p></body></html>",
                content_type='text/html'
            )

        if not code:
            return web.Response(
                text="<html><body><h1>Login Failed</h1><p>No authorization code received</p></body></html>",
                content_type='text/html'
            )

        # Check if this is a Device Flow OAuth callback
        if state:
            try:
                from core.auth import get_device_flow_handler
                device_flow = get_device_flow_handler()

                if device_flow:
                    # Check if state is associated with a device code
                    device_code = await device_flow.storage.get_by_oauth_state(state)

                    if device_code:
                        # This is a Device Flow callback - delegate to device flow handler
                        logger.info(f"Device Flow OAuth callback detected: state={state[:15]}...")
                        return await self._handle_device_flow_callback(request, code, state, device_code)
            except Exception as e:
                logger.warning(f"Error checking device flow state: {e}")
                # Continue with normal Secrets UI flow

        try:
            # Exchange code for tokens
            async with ClientSession() as session:
                token_data = {
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code"
                }

                async with session.post(GOOGLE_TOKEN_URL, data=token_data) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"Token exchange failed: {error_text}")
                        return web.Response(
                            text="<html><body><h1>Login Failed</h1><p>Token exchange failed</p></body></html>",
                            content_type='text/html'
                        )

                    tokens = await resp.json()
                    access_token = tokens.get('access_token')

                # Get user info
                headers = {"Authorization": f"Bearer {access_token}"}
                async with session.get(GOOGLE_USERINFO_URL, headers=headers) as resp:
                    if resp.status != 200:
                        return web.Response(
                            text="<html><body><h1>Login Failed</h1><p>Failed to get user info</p></body></html>",
                            content_type='text/html'
                        )

                    user_info = await resp.json()

            # Verify domain
            email = user_info.get('email', '')
            if not email.endswith(f"@{ALLOWED_DOMAIN}"):
                logger.warning(f"Login attempt from unauthorized domain: {email}")
                return web.Response(
                    text=f"<html><body><h1>Access Denied</h1><p>Only {ALLOWED_DOMAIN} accounts are allowed</p></body></html>",
                    content_type='text/html',
                    status=403
                )

            # Create JWT token
            token_data = {
                "sub": email,
                "name": user_info.get('name', ''),
                "picture": user_info.get('picture', ''),
                "email": email
            }
            jwt_token = self.create_access_token(token_data)

            # Return HTML with token that JavaScript will store
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Login Successful</title>
                <script>
                    // Store token in localStorage
                    localStorage.setItem('auth_token', '{jwt_token}');
                    localStorage.setItem('user_email', '{email}');
                    localStorage.setItem('user_name', '{user_info.get("name", "")}');
                    localStorage.setItem('user_picture', '{user_info.get("picture", "")}');

                    // Redirect to dashboard
                    window.location.href = '/secrets/dashboard';
                </script>
            </head>
            <body>
                <h1>Login Successful!</h1>
                <p>Redirecting to dashboard...</p>
            </body>
            </html>
            """

            return web.Response(text=html, content_type='text/html')

        except Exception as e:
            logger.error(f"OAuth callback error: {e}", exc_info=True)
            return web.Response(
                text=f"<html><body><h1>Login Failed</h1><p>Error: {str(e)}</p></body></html>",
                content_type='text/html'
            )

    async def _handle_device_flow_callback(self, request: web.Request, code: str, state: str, device_code: str):
        """Handle Device Flow OAuth callback"""
        try:
            from core.auth import get_device_flow_handler, get_oauth_handler

            device_flow = get_device_flow_handler()
            oauth_handler = get_oauth_handler()

            if not device_flow or not oauth_handler:
                logger.error("Device flow or OAuth handler not available")
                return web.Response(
                    text="<html><body><h1>Service Error</h1><p>Authentication service not configured</p></body></html>",
                    content_type='text/html',
                    status=503
                )

            # Exchange code for token and get user info
            try:
                user_info = await oauth_handler.handle_callback(code)
                logger.info(f"OAuth successful for device flow user: {user_info.get('email')}")
            except Exception as e:
                logger.error(f"OAuth token exchange failed for device flow: {e}")
                return web.Response(
                    text=f"<html><body><h1>Authentication Failed</h1><p>Could not complete Google authentication</p></body></html>",
                    content_type='text/html',
                    status=400
                )

            # Get device info to retrieve user_code
            device_info = await device_flow.storage.get(device_code)

            if not device_info:
                logger.warning(f"Device info not found for device_code: {device_code[:15]}...")
                return web.Response(
                    text="<html><body><h1>Session Expired</h1><p>Your device authorization session has expired. Please try again.</p></body></html>",
                    content_type='text/html',
                    status=400
                )

            user_code = device_info.get("user_code")

            # Approve the device
            success = await device_flow.approve_device(user_code, user_info)

            if success:
                logger.info(f"Device approved successfully: user_code={user_code}, user={user_info.get('email')}")

                # Return success page
                return web.Response(
                    text="""<!DOCTYPE html>
                    <html>
                    <head>
                        <title>Device Authorized</title>
                        <style>
                            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; }
                            .container { background: white; padding: 60px 40px; border-radius: 16px; box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3); max-width: 520px; }
                            .success { color: #4CAF50; font-size: 64px; margin-bottom: 20px; }
                            h1 { color: #1a202c; margin-bottom: 12px; }
                            p { color: #718096; font-size: 18px; margin: 10px 0; }
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <div class="success">✓</div>
                            <h1>Device Authorized Successfully</h1>
                            <p>You can now close this window and return to your device.</p>
                            <p>Your CLI will automatically receive the access token.</p>
                        </div>
                    </body>
                    </html>""",
                    content_type='text/html',
                    status=200
                )
            else:
                logger.error(f"Failed to approve device: user_code={user_code}")
                return web.Response(
                    text="<html><body><h1>Authorization Failed</h1><p>Could not authorize your device. Please try again.</p></body></html>",
                    content_type='text/html',
                    status=500
                )

        except Exception as e:
            logger.error(f"Error in device flow callback: {e}", exc_info=True)
            return web.Response(
                text=f"<html><body><h1>Error</h1><p>An error occurred: {str(e)}</p></body></html>",
                content_type='text/html',
                status=500
            )

    async def logout(self, request: web.Request):
        """Logout endpoint"""
        return web.json_response({"message": "Logged out successfully"})

    async def login_page(self, request: web.Request):
        """Render login page"""
        html = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Login - NubemSuperFClaude Secrets</title>
            <link href="https://cdn.jsdelivr.net/npm/tailwindcss@3/dist/tailwind.min.css" rel="stylesheet">
        </head>
        <body class="bg-gray-100">
            <div class="min-h-screen flex items-center justify-center">
                <div class="bg-white p-8 rounded-lg shadow-lg max-w-md w-full">
                    <div class="text-center mb-8">
                        <h1 class="text-3xl font-bold text-gray-800 mb-2">NubemSuperFClaude</h1>
                        <p class="text-gray-600">Secrets Management</p>
                    </div>

                    <div class="mb-6">
                        <p class="text-sm text-gray-600 text-center mb-4">
                            Sign in with your <strong>@nubemsystems.es</strong> account
                        </p>
                    </div>

                    <a href="/auth/google"
                       class="flex items-center justify-center w-full bg-white border border-gray-300 rounded-lg px-6 py-3 text-gray-700 font-medium hover:bg-gray-50 transition">
                        <svg class="w-5 h-5 mr-3" viewBox="0 0 24 24">
                            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                        </svg>
                        Sign in with Google
                    </a>

                    <div class="mt-6 text-center text-sm text-gray-500">
                        <p>Secure access to secrets management</p>
                        <p class="mt-2">Powered by Google OAuth2</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        return web.Response(text=html, content_type='text/html')

    # ==================== API Endpoints (CRUD) ====================

    async def list_secrets(self, request: web.Request):
        """List all secrets for the current user"""
        try:
            user = await self.require_user(request)

            # Use real SecretsManager.list_secrets()
            secret_names = secrets_manager.list_secrets(user_email=user['email'])

            secrets_list = [{"name": name} for name in secret_names]

            # Check if request is from htmx
            if request.headers.get("HX-Request"):
                # Return HTML template
                context = {
                    "request": request,
                    "secrets": secrets_list
                }
                return aiohttp_jinja2.render_template('secrets.html', request, context)

            # Return JSON
            return web.json_response(secrets_list)

        except web.HTTPUnauthorized:
            raise
        except Exception as e:
            logger.error(f"Error listing secrets: {e}", exc_info=True)
            return web.json_response(
                {"detail": f"Failed to list secrets: {str(e)}"},
                status=500
            )

    async def get_secret(self, request: web.Request):
        """Get a specific secret value"""
        try:
            user = await self.require_user(request)
            secret_name = request.match_info['secret_name']

            secret_value = secrets_manager.get_secret(secret_name, user_email=user['email'])

            if secret_value is None:
                return web.json_response(
                    {"detail": f"Secret '{secret_name}' not found"},
                    status=404
                )

            return web.json_response({
                "name": secret_name,
                "value": secret_value
            })

        except web.HTTPUnauthorized:
            raise
        except Exception as e:
            logger.error(f"Error getting secret: {e}", exc_info=True)
            return web.json_response(
                {"detail": f"Failed to get secret: {str(e)}"},
                status=500
            )

    async def create_secret(self, request: web.Request):
        """Create a new secret"""
        try:
            user = await self.require_user(request)
            data = await request.json()

            secret_name = data.get('name')
            secret_value = data.get('value')
            labels = data.get('labels')

            if not secret_name or not secret_value:
                return web.json_response(
                    {"detail": "name and value are required"},
                    status=400
                )

            # Use real SecretsManager.create_secret()
            success = secrets_manager.create_secret(
                secret_name=secret_name,
                secret_value=secret_value,
                user_email=user['email'],
                labels=labels
            )

            if not success:
                return web.json_response(
                    {"detail": "Failed to create secret"},
                    status=500
                )

            return web.json_response({
                "name": secret_name,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "labels": labels,
                "message": "Secret created successfully"
            }, status=201)

        except web.HTTPUnauthorized:
            raise
        except Exception as e:
            logger.error(f"Error creating secret: {e}", exc_info=True)
            return web.json_response(
                {"detail": f"Failed to create secret: {str(e)}"},
                status=500
            )

    async def update_secret(self, request: web.Request):
        """Update an existing secret"""
        try:
            user = await self.require_user(request)
            secret_name = request.match_info['secret_name']
            data = await request.json()

            secret_value = data.get('value')
            if not secret_value:
                return web.json_response(
                    {"detail": "value is required"},
                    status=400
                )

            # Use real SecretsManager.update_secret()
            success = secrets_manager.update_secret(
                secret_name=secret_name,
                secret_value=secret_value,
                user_email=user['email']
            )

            if not success:
                return web.json_response(
                    {"detail": "Failed to update secret"},
                    status=500
                )

            return web.json_response({
                "name": secret_name,
                "updated_at": datetime.utcnow().isoformat() + "Z",
                "message": "Secret updated successfully"
            })

        except web.HTTPUnauthorized:
            raise
        except Exception as e:
            logger.error(f"Error updating secret: {e}", exc_info=True)
            return web.json_response(
                {"detail": f"Failed to update secret: {str(e)}"},
                status=500
            )

    async def delete_secret(self, request: web.Request):
        """Delete a secret"""
        try:
            user = await self.require_user(request)
            secret_name = request.match_info['secret_name']

            # Use real SecretsManager.delete_secret()
            success = secrets_manager.delete_secret(
                secret_name=secret_name,
                user_email=user['email']
            )

            if not success:
                return web.json_response(
                    {"detail": "Failed to delete secret"},
                    status=500
                )

            return web.Response(status=204)

        except web.HTTPUnauthorized:
            raise
        except Exception as e:
            logger.error(f"Error deleting secret: {e}", exc_info=True)
            return web.json_response(
                {"detail": f"Failed to delete secret: {str(e)}"},
                status=500
            )

    async def get_current_user_info(self, request: web.Request):
        """Get current user information"""
        try:
            user = await self.require_user(request)
            return web.json_response(user)
        except web.HTTPUnauthorized:
            raise
        except Exception as e:
            logger.error(f"Error getting user info: {e}", exc_info=True)
            return web.json_response(
                {"detail": f"Failed to get user info: {str(e)}"},
                status=500
            )

    # ==================== UI Endpoints ====================

    @aiohttp_jinja2.template('dashboard.html')
    async def secrets_dashboard(self, request: web.Request):
        """Render secrets dashboard UI"""
        # Check for token in query param (for development/testing)
        # In production, frontend JavaScript will handle auth
        return {
            "request": request,
            "google_client_id": GOOGLE_CLIENT_ID,
            "allowed_domain": ALLOWED_DOMAIN
        }


def setup_secrets_ui(app: web.Application):
    """
    Setup function to be called from main server

    Usage:
        from mcp_server.secrets_ui_routes import setup_secrets_ui
        setup_secrets_ui(app)
    """
    SecretsUIRoutes(app)
    logger.info("🔐 Secrets UI integrated successfully with Google OAuth2")

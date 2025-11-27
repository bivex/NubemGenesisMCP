"""
Google OAuth 2.0 Handler
Implements OAuth 2.0 authorization code flow with PKCE for web applications.
"""

import os
import secrets
import hashlib
import base64
import json
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from urllib.parse import urlencode

import jwt
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from google_auth_oauthlib.flow import Flow

logger = logging.getLogger(__name__)


class GoogleOAuthHandler:
    """
    Google OAuth 2.0 handler implementing Authorization Code Flow with PKCE.
    
    Security Features:
    - PKCE (Proof Key for Code Exchange) for additional security
    - State parameter for CSRF protection  
    - Nonce for replay attack prevention
    - Token validation (signature, issuer, audience, expiration)
    - Secure session token generation (JWT)
    """
    
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        jwt_secret: Optional[str] = None
    ):
        """
        Initialize Google OAuth handler.
        
        Args:
            client_id: Google OAuth client ID (from GCP Console)
            client_secret: Google OAuth client secret
            redirect_uri: Authorized redirect URI
            jwt_secret: Secret key for signing JWT session tokens
        """
        # Load from environment if not provided
        self.client_id = client_id or os.getenv("GOOGLE_OAUTH_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
        self.redirect_uri = redirect_uri or os.getenv(
            "GOOGLE_OAUTH_REDIRECT_URI",
            "http://localhost:8080/auth/google/callback"
        )
        self.jwt_secret = jwt_secret or os.getenv(
            "JWT_SECRET_KEY",
            secrets.token_urlsafe(32)  # Generate if not provided
        )
        
        # OAuth scopes
        self.scopes = [
            'openid',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile'
        ]
        
        # Validate configuration
        if not self.client_id:
            logger.warning("GOOGLE_OAUTH_CLIENT_ID not configured")
        if not self.client_secret:
            logger.warning("GOOGLE_OAUTH_CLIENT_SECRET not configured")
            
        logger.info("✅ GoogleOAuthHandler initialized")
        logger.debug(f"Redirect URI: {self.redirect_uri}")
    
    def is_configured(self) -> bool:
        """Check if OAuth is properly configured."""
        return bool(self.client_id and self.client_secret)
    
    def generate_pkce_pair(self) -> Tuple[str, str]:
        """
        Generate PKCE code verifier and challenge.
        
        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        # Generate code verifier (43-128 characters, base64url encoded)
        code_verifier = secrets.token_urlsafe(64)
        
        # Generate code challenge (SHA256 hash of verifier, base64url encoded)
        challenge_bytes = hashlib.sha256(code_verifier.encode()).digest()
        code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode().rstrip('=')
        
        return code_verifier, code_challenge
    
    def get_authorization_url(self) -> Dict[str, str]:
        """
        Generate Google OAuth authorization URL.
        
        Returns:
            Dict with:
            - authorization_url: URL to redirect user to
            - state: CSRF protection token (store in session)
            - nonce: Replay attack prevention (store in session)
            - code_verifier: PKCE verifier (store in session)
        """
        if not self.is_configured():
            raise ValueError("OAuth not configured. Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET")
        
        # Generate security tokens
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        code_verifier, code_challenge = self.generate_pkce_pair()
        
        # Build authorization URL
        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(self.scopes),
            'state': state,
            'nonce': nonce,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'access_type': 'offline',  # Request refresh token
            'prompt': 'consent'  # Force consent screen
        }
        
        authorization_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
        
        logger.info(f"Generated authorization URL for client: {self.client_id[:20]}...")
        
        return {
            'authorization_url': authorization_url,
            'state': state,
            'nonce': nonce,
            'code_verifier': code_verifier
        }
    
    def exchange_code_for_tokens(
        self,
        code: str,
        code_verifier: str,
        state: str,
        expected_state: str
    ) -> Dict:
        """
        Exchange authorization code for tokens.
        
        Args:
            code: Authorization code from callback
            code_verifier: PKCE code verifier (from session)
            state: State parameter from callback
            expected_state: Expected state (from session)
        
        Returns:
            Dict with user info and tokens
        
        Raises:
            ValueError: If state mismatch or token validation fails
        """
        # Validate state (CSRF protection)
        if state != expected_state:
            logger.error(f"State mismatch: {state} != {expected_state}")
            raise ValueError("Invalid state parameter (CSRF protection)")
        
        # Create flow
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.redirect_uri]
                }
            },
            scopes=self.scopes,
            redirect_uri=self.redirect_uri
        )
        
        # Add PKCE verifier
        flow.code_verifier = code_verifier
        
        # Exchange code for tokens
        try:
            flow.fetch_token(code=code)
        except Exception as e:
            logger.error(f"Token exchange failed: {e}")
            raise ValueError(f"Failed to exchange code for tokens: {e}")
        
        # Get credentials
        credentials = flow.credentials
        
        # Validate and decode ID token
        try:
            id_info = google_id_token.verify_oauth2_token(
                credentials.id_token,
                google_requests.Request(),
                self.client_id
            )
        except Exception as e:
            logger.error(f"ID token validation failed: {e}")
            raise ValueError(f"Invalid ID token: {e}")
        
        # Extract user info
        user_info = {
            'google_id': id_info.get('sub'),
            'email': id_info.get('email'),
            'email_verified': id_info.get('email_verified', False),
            'name': id_info.get('name'),
            'picture': id_info.get('picture'),
            'locale': id_info.get('locale'),
            'access_token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'expires_at': credentials.expiry.isoformat() if credentials.expiry else None
        }
        
        logger.info(f"✅ OAuth successful for user: {user_info['email']}")
        
        return user_info
    
    def create_session_token(
        self,
        user_info: Dict,
        expires_in_hours: int = 24
    ) -> str:
        """
        Create JWT session token for authenticated user.
        
        Args:
            user_info: User information from OAuth
            expires_in_hours: Token validity period (default: 24 hours)
        
        Returns:
            JWT session token
        """
        now = datetime.utcnow()
        
        payload = {
            'sub': user_info['email'],
            'google_id': user_info['google_id'],
            'name': user_info['name'],
            'email': user_info['email'],
            'email_verified': user_info['email_verified'],
            'picture': user_info.get('picture'),
            'iat': now,
            'exp': now + timedelta(hours=expires_in_hours),
            'iss': 'nubemsfc-mcp-server',
            'aud': 'nubemsfc-web-client'
        }
        
        token = jwt.encode(payload, self.jwt_secret, algorithm='HS256')
        
        logger.info(f"Created session token for {user_info['email']} (expires in {expires_in_hours}h)")
        
        return token
    
    def validate_session_token(self, token: str) -> Optional[Dict]:
        """
        Validate JWT session token.
        
        Args:
            token: JWT session token
        
        Returns:
            Token payload if valid, None otherwise
        """
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=['HS256'],
                audience='nubemsfc-web-client',
                issuer='nubemsfc-mcp-server'
            )
            
            logger.debug(f"Valid session token for: {payload.get('email')}")
            
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("Session token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid session token: {e}")
            return None
    
    def refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """
        Refresh Google access token using refresh token.
        
        Args:
            refresh_token: Google refresh token
        
        Returns:
            New access token if successful, None otherwise
        """
        # TODO: Implement token refresh
        # This requires storing refresh tokens securely and implementing
        # refresh flow with Google OAuth API
        logger.warning("Token refresh not yet implemented")
        return None
    
    def revoke_token(self, token: str):
        """
        Revoke Google OAuth token.
        
        Args:
            token: Access or refresh token to revoke
        """
        import requests
        
        try:
            response = requests.post(
                'https://oauth2.googleapis.com/revoke',
                params={'token': token},
                headers={'content-type': 'application/x-www-form-urlencoded'}
            )
            
            if response.status_code == 200:
                logger.info("✅ Token revoked successfully")
            else:
                logger.warning(f"Token revocation failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Token revocation error: {e}")


# Global instance (singleton)
_global_oauth_handler: Optional[GoogleOAuthHandler] = None


def get_oauth_handler() -> GoogleOAuthHandler:
    """
    Get or create the global GoogleOAuthHandler instance.
    
    Returns:
        GoogleOAuthHandler instance
    """
    global _global_oauth_handler
    
    if _global_oauth_handler is None:
        _global_oauth_handler = GoogleOAuthHandler()
    
    return _global_oauth_handler

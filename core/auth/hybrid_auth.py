"""
Hybrid Authentication Manager
Supports both API Keys and OAuth 2.0 tokens for flexible authentication.
"""

import logging
from typing import Dict, Optional, Tuple

from .user_auth_manager import UserAuthManager, get_auth_manager
from .oauth_handler import GoogleOAuthHandler, get_oauth_handler

logger = logging.getLogger(__name__)


class HybridAuthManager:
    """
    Hybrid authentication manager supporting multiple authentication methods:
    1. API Key authentication (X-API-Key header)
    2. OAuth 2.0 Bearer token authentication (Authorization: Bearer header)
    
    This allows:
    - Technical users / automation → API keys
    - Web UI users → OAuth tokens
    - Both can coexist in the same system
    """
    
    def __init__(
        self,
        api_key_manager: Optional[UserAuthManager] = None,
        oauth_handler: Optional[GoogleOAuthHandler] = None
    ):
        """
        Initialize hybrid auth manager.
        
        Args:
            api_key_manager: UserAuthManager instance (defaults to global)
            oauth_handler: GoogleOAuthHandler instance (defaults to global)
        """
        self.api_key_manager = api_key_manager or get_auth_manager()
        self.oauth_handler = oauth_handler or get_oauth_handler()
        
        logger.info("✅ HybridAuthManager initialized")
        logger.info(f"  - API Key auth: enabled")
        logger.info(f"  - OAuth auth: {'enabled' if self.oauth_handler.is_configured() else 'disabled (not configured)'}")
    
    async def authenticate(self, headers: Dict[str, str]) -> Tuple[bool, Optional[Dict], str]:
        """
        Authenticate request using API key or OAuth token.
        
        Args:
            headers: HTTP request headers
        
        Returns:
            Tuple of (success: bool, user_info: Dict or None, auth_type: str)
            
            auth_type values:
            - "api_key" - Authenticated with API key
            - "oauth" - Authenticated with OAuth token
            - "none" - No authentication provided
            - "invalid" - Authentication failed
        """
        # Try API key authentication first (X-API-Key header)
        api_key = headers.get('X-API-Key', '').strip()
        
        if api_key:
            user = self.api_key_manager.validate_api_key(api_key)
            
            if user:
                logger.info(f"✅ API key authentication successful: {user.get('user_email')}")
                return True, user, "api_key"
            else:
                logger.warning(f"❌ Invalid API key: {api_key[:15]}...")
                return False, None, "invalid"
        
        # Try OAuth Bearer token authentication
        auth_header = headers.get('Authorization', '').strip()
        
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]  # Remove "Bearer " prefix
            
            if not self.oauth_handler.is_configured():
                logger.warning("OAuth token provided but OAuth not configured")
                return False, None, "invalid"
            
            # Validate JWT session token
            payload = self.oauth_handler.validate_session_token(token)
            
            if payload:
                # Convert OAuth payload to user format
                user = {
                    'user_email': payload.get('email'),
                    'role': self._determine_oauth_role(payload),
                    'auth_method': 'oauth',
                    'google_id': payload.get('google_id'),
                    'name': payload.get('name'),
                    'email_verified': payload.get('email_verified', False)
                }
                
                logger.info(f"✅ OAuth authentication successful: {user.get('user_email')}")
                return True, user, "oauth"
            else:
                logger.warning("❌ Invalid or expired OAuth token")
                return False, None, "invalid"
        
        # No authentication provided
        logger.debug("No authentication credentials provided")
        return False, None, "none"
    
    def _determine_oauth_role(self, oauth_payload: Dict) -> str:
        """
        Determine user role based on OAuth payload.
        
        Args:
            oauth_payload: JWT payload from OAuth token
        
        Returns:
            Role string (admin, readonly, etc.)
        """
        email = oauth_payload.get('email', '')
        
        # Define admin users (can be moved to config)
        ADMIN_EMAILS = [
            'david.anguera@nubemsystems.es',
            # Add more admin emails here
        ]
        
        if email in ADMIN_EMAILS:
            return 'admin'
        
        # Default role for authenticated OAuth users
        return 'readonly'
    
    def get_user_rate_limit(self, user: Dict) -> Dict[str, int]:
        """
        Get rate limit configuration for user.
        
        Args:
            user: User info dict
        
        Returns:
            Dict with requests_per_minute and burst
        """
        # Use API key manager's rate limit logic
        return self.api_key_manager.get_user_rate_limit(user)
    
    def check_permission(
        self,
        user: Dict,
        mcp_name: str,
        operation: str = "read"
    ) -> bool:
        """
        Check if user has permission for MCP operation.
        
        Args:
            user: User info dict from authenticate()
            mcp_name: Name of MCP
            operation: Operation type (read, write, delete, execute)
        
        Returns:
            True if authorized, False otherwise
        """
        # Use API key manager's permission logic
        return self.api_key_manager.check_permission(user, mcp_name, operation)


# Global instance (singleton)
_global_hybrid_auth: Optional[HybridAuthManager] = None


def get_hybrid_auth_manager() -> HybridAuthManager:
    """
    Get or create the global HybridAuthManager instance.
    
    Returns:
        HybridAuthManager instance
    """
    global _global_hybrid_auth
    
    if _global_hybrid_auth is None:
        _global_hybrid_auth = HybridAuthManager()
    
    return _global_hybrid_auth

"""
User Authentication Manager
Extends MCPCredentialsManager pattern for user authentication and authorization.
"""

import json
import logging
import hashlib
from typing import Dict, Optional, List
from datetime import datetime

# Import existing MCPCredentialsManager
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_integration.mcp_credentials_manager import MCPCredentialsManager

logger = logging.getLogger(__name__)


class UserAuthManager:
    """
    Manages user authentication and authorization.

    Integrates with:
    - GCP Secret Manager (via External Secrets Operator)
    - Kubernetes secrets
    - In-memory caching

    Reuses the same pattern as MCPCredentialsManager for consistency.
    """

    def __init__(self, credentials_manager: Optional[MCPCredentialsManager] = None):
        """
        Initialize UserAuthManager.

        Args:
            credentials_manager: Existing MCPCredentialsManager instance (reuses infrastructure)
        """
        self.creds_manager = credentials_manager or MCPCredentialsManager(
            namespace="production",
            cache_ttl_seconds=300
        )

        # Cache: {api_key_hash: user_info}
        self._users_cache: Dict[str, Dict] = {}
        self._roles_cache: Optional[Dict] = None

        logger.info("✅ UserAuthManager initialized (reusing MCPCredentialsManager)")

    def _hash_api_key(self, api_key: str) -> str:
        """
        Hash API key for secure caching.

        Args:
            api_key: Full API key

        Returns:
            SHA256 hash of the key
        """
        return hashlib.sha256(api_key.encode()).hexdigest()[:16]

    def _load_user_from_k8s(self, role: str) -> Optional[Dict]:
        """
        Load user configuration from Kubernetes secret or environment variable.

        Args:
            role: User role (admin, readonly)

        Returns:
            User configuration dict or None
        """
        secret_name = f"mcp-auth-{role}"
        env_var_name = f"MCP_AUTH_{role.upper()}_CONFIG"

        # Try K8s first
        user_json = self.creds_manager.get_secret_from_k8s(secret_name, "user_config")

        # Fallback to environment variable
        if not user_json:
            user_json = self.creds_manager.get_secret_from_env(env_var_name)

        if not user_json:
            logger.warning(f"User config for role {role} not found in K8s or env ({env_var_name})")
            return None

        try:
            user_config = json.loads(user_json)
            logger.info(f"✅ Loaded user config for role: {role}")
            return user_config
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config for {role}: {e}")
            return None

    def _load_roles_config(self) -> Dict:
        """
        Load roles configuration from Kubernetes secret or environment variable.

        Returns:
            Roles configuration dict
        """
        if self._roles_cache:
            logger.debug("Returning cached roles config")
            return self._roles_cache

        # Try loading from K8s secret (YAML format)
        roles_yaml = self.creds_manager.get_secret_from_k8s("mcp-auth-roles", "roles.yaml")

        if roles_yaml:
            try:
                import yaml
                self._roles_cache = yaml.safe_load(roles_yaml)
                logger.info(f"✅ Loaded roles config from K8s: {list(self._roles_cache.get('roles', {}).keys())}")
                return self._roles_cache
            except Exception as e:
                logger.error(f"Error parsing roles YAML from K8s: {e}")

        # Fallback to environment variable (JSON format)
        roles_json = self.creds_manager.get_secret_from_env("MCP_AUTH_ROLES_CONFIG")

        if roles_json:
            try:
                self._roles_cache = json.loads(roles_json)
                logger.info(f"✅ Loaded roles config from env: {list(self._roles_cache.get('roles', {}).keys())}")
                return self._roles_cache
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing roles JSON from env: {e}")

        # Use defaults if nothing works
        logger.warning("Roles config not found in K8s or env, using defaults")
        return self._get_default_roles()

    def validate_api_key(self, api_key: str) -> Optional[Dict]:
        """
        Validate API key and return user information.

        Args:
            api_key: API key from X-API-Key header

        Returns:
            User info dict with keys: api_key, user_email, role, active, created_at, expires_at
            None if invalid or inactive
        """
        if not api_key or not api_key.strip():
            logger.warning("Empty API key provided")
            return None

        # Check cache first
        key_hash = self._hash_api_key(api_key)
        if key_hash in self._users_cache:
            user = self._users_cache[key_hash]
            logger.debug(f"Cache hit for user: {user.get('user_email')}")
            return user

        # Load all users and check
        for role in ["admin", "readonly"]:
            user = self._load_user_from_k8s(role)

            if user and user.get("api_key") == api_key:
                # Check if active
                if not user.get("active", True):
                    logger.warning(f"❌ User {user.get('user_email')} is inactive")
                    return None

                # Check expiration
                expires_at = user.get("expires_at")
                if expires_at:
                    try:
                        expires_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                        if datetime.now(expires_dt.tzinfo) > expires_dt:
                            logger.warning(f"❌ API key expired for {user.get('user_email')}")
                            return None
                    except:
                        pass  # If can't parse, allow access

                # Cache it
                self._users_cache[key_hash] = user
                logger.info(f"✅ Valid API key for user: {user.get('user_email')} (role: {user.get('role')})")
                return user

        # Invalid key
        logger.warning(f"❌ Invalid API key: {api_key[:15]}...")
        return None

    def check_permission(
        self,
        user: Dict,
        mcp_name: str,
        operation: str = "read"
    ) -> bool:
        """
        Check if user has permission for MCP operation.

        Args:
            user: User info dict from validate_api_key()
            mcp_name: Name of MCP (e.g., "kubernetes", "intelligent_respond")
            operation: Operation type (read, write, delete, execute)

        Returns:
            True if authorized, False otherwise
        """
        role = user.get("role")
        if not role:
            logger.warning("User has no role assigned")
            return False

        # Load roles configuration
        roles_config = self._load_roles_config()
        role_perms = roles_config.get("roles", {}).get(role, {}).get("permissions", {})

        if not role_perms:
            logger.warning(f"No permissions found for role: {role}")
            return False

        # Check if MCP is explicitly blocked
        blocked_mcps = role_perms.get("blocked_mcps", [])
        if mcp_name in blocked_mcps:
            logger.warning(
                f"❌ DENIED: User {user.get('user_email')} (role: {role}) "
                f"attempted to access blocked MCP: {mcp_name}"
            )
            return False

        # Check if MCP is in allowed list
        allowed_mcps = role_perms.get("mcps", [])

        # "*" means all MCPs allowed (admin)
        if "*" in allowed_mcps:
            logger.debug(f"✅ User {user.get('user_email')} has wildcard access")
        elif mcp_name not in allowed_mcps:
            logger.warning(
                f"❌ DENIED: User {user.get('user_email')} (role: {role}) "
                f"attempted to access unauthorized MCP: {mcp_name}"
            )
            return False

        # Check operation permission
        allowed_operations = role_perms.get("operations", [])
        if operation not in allowed_operations:
            logger.warning(
                f"❌ DENIED: User {user.get('user_email')} (role: {role}) "
                f"attempted unauthorized operation '{operation}' on MCP: {mcp_name}"
            )
            return False

        logger.info(
            f"✅ ALLOWED: User {user.get('user_email')} (role: {role}) "
            f"→ {operation} on {mcp_name}"
        )
        return True

    def get_user_rate_limit(self, user: Dict) -> Dict[str, int]:
        """
        Get rate limit configuration for user.

        Args:
            user: User info dict

        Returns:
            Dict with requests_per_minute and burst
        """
        role = user.get("role")
        roles_config = self._load_roles_config()

        rate_limit = roles_config.get("roles", {}).get(role, {}).get("rate_limit", {})

        return {
            "requests_per_minute": rate_limit.get("requests_per_minute", 10),
            "burst": rate_limit.get("burst", 2)
        }

    def _get_default_roles(self) -> Dict:
        """
        Default roles configuration (fallback).

        Returns:
            Default roles dict
        """
        return {
            "roles": {
                "admin": {
                    "permissions": {
                        "mcps": ["*"],
                        "operations": ["read", "write", "delete", "execute"],
                        "blocked_mcps": []
                    },
                    "rate_limit": {
                        "requests_per_minute": 100,
                        "burst": 20
                    }
                },
                "readonly": {
                    "permissions": {
                        "mcps": [
                            "intelligent_respond",
                            "list_personas",
                            "get_system_status",
                            "semantic_similarity"
                        ],
                        "operations": ["read"],
                        "blocked_mcps": [
                            "kubernetes", "docker", "gcp", "github", "filesystem"
                        ]
                    },
                    "rate_limit": {
                        "requests_per_minute": 30,
                        "burst": 5
                    }
                }
            }
        }

    def clear_cache(self):
        """Clear user cache (useful for testing or key rotation)."""
        self._users_cache.clear()
        self._roles_cache = None
        self.creds_manager.clear_cache()
        logger.info("🗑️ User auth cache cleared")

    def get_cache_stats(self) -> Dict:
        """
        Get cache statistics.

        Returns:
            Dict with cache stats
        """
        return {
            "users_cached": len(self._users_cache),
            "roles_cached": self._roles_cache is not None,
            "credentials_cache": self.creds_manager.get_cache_stats()
        }


# Global instance (singleton pattern like MCPCredentialsManager)
_global_auth_manager: Optional[UserAuthManager] = None


def get_auth_manager(credentials_manager: Optional[MCPCredentialsManager] = None) -> UserAuthManager:
    """
    Get or create the global UserAuthManager instance.

    Args:
        credentials_manager: Optional MCPCredentialsManager to reuse

    Returns:
        UserAuthManager instance
    """
    global _global_auth_manager

    if _global_auth_manager is None:
        _global_auth_manager = UserAuthManager(credentials_manager)

    return _global_auth_manager

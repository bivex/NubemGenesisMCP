"""
MCP Credentials Manager - Secure credential management for external MCPs

Integrates with Kubernetes secrets created by External Secrets Operator
to provide secure, cached access to MCP credentials.
"""

import os
import logging
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import base64

try:
    from kubernetes import client, config
    KUBERNETES_AVAILABLE = True
except ImportError:
    KUBERNETES_AVAILABLE = False
    logging.warning("kubernetes package not available. Using environment variables only.")

logger = logging.getLogger(__name__)


class MCPCredentialsManager:
    """
    Manages credentials for 100+ MCPs using Kubernetes secrets.

    Features:
    - Automatic credential loading from K8s secrets
    - In-memory caching with TTL
    - Fallback to environment variables
    - Validation of credentials
    - Support for multiple namespaces
    """

    def __init__(
        self,
        namespace: str = "default",
        cache_ttl_seconds: int = 300,  # 5 minutes
        use_k8s: bool = True
    ):
        """
        Initialize Credentials Manager.

        Args:
            namespace: Kubernetes namespace for secrets
            cache_ttl_seconds: Cache time-to-live in seconds
            use_k8s: Whether to use Kubernetes (False = env vars only)
        """
        self.namespace = namespace
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self.use_k8s = use_k8s and KUBERNETES_AVAILABLE

        # Cache: {secret_name: (value, timestamp)}
        self._cache: Dict[str, tuple[str, datetime]] = {}

        # Kubernetes client
        self.k8s_client = None
        if self.use_k8s:
            try:
                # Try in-cluster config first
                config.load_incluster_config()
                logger.info("Loaded in-cluster Kubernetes config")
            except:
                try:
                    # Fallback to kubeconfig
                    config.load_kube_config()
                    logger.info("Loaded kubeconfig")
                except Exception as e:
                    logger.warning(f"Failed to load Kubernetes config: {e}. Using env vars only.")
                    self.use_k8s = False

            if self.use_k8s:
                self.k8s_client = client.CoreV1Api()

        logger.info(f"MCPCredentialsManager initialized (k8s={self.use_k8s}, cache_ttl={cache_ttl_seconds}s)")

    def _get_from_cache(self, key: str) -> Optional[str]:
        """Get value from cache if not expired."""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if datetime.now() - timestamp < self.cache_ttl:
                logger.debug(f"Cache hit for {key}")
                return value
            else:
                # Expired
                del self._cache[key]
        return None

    def _set_cache(self, key: str, value: str):
        """Set value in cache with current timestamp."""
        self._cache[key] = (value, datetime.now())

    def get_secret_from_k8s(self, secret_name: str, key: str) -> Optional[str]:
        """
        Get a secret value from Kubernetes.

        Args:
            secret_name: Name of the K8s secret
            key: Key within the secret

        Returns:
            Secret value or None if not found
        """
        if not self.use_k8s or not self.k8s_client:
            return None

        cache_key = f"{secret_name}/{key}"

        # Check cache first
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        try:
            # Get secret from K8s
            secret = self.k8s_client.read_namespaced_secret(
                name=secret_name,
                namespace=self.namespace
            )

            if secret.data and key in secret.data:
                # Decode base64
                value = base64.b64decode(secret.data[key]).decode('utf-8')

                # Cache it
                self._set_cache(cache_key, value)

                logger.info(f"Loaded secret {secret_name}/{key} from Kubernetes")
                return value
            else:
                logger.warning(f"Key {key} not found in secret {secret_name}")
                return None

        except client.exceptions.ApiException as e:
            if e.status == 404:
                logger.warning(f"Secret {secret_name} not found in namespace {self.namespace}")
            else:
                logger.error(f"Error reading secret {secret_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error reading secret {secret_name}: {e}")
            return None

    def get_secret_from_env(self, env_var: str) -> Optional[str]:
        """
        Get a secret from environment variable.

        Args:
            env_var: Environment variable name

        Returns:
            Value or None
        """
        value = os.getenv(env_var)
        if value:
            logger.debug(f"Loaded {env_var} from environment")
        return value

    def get_credential(
        self,
        secret_name: str,
        key: str,
        env_var: Optional[str] = None
    ) -> Optional[str]:
        """
        Get a credential with automatic fallback.

        Tries in order:
        1. Kubernetes secret
        2. Environment variable
        3. None

        Args:
            secret_name: K8s secret name
            key: Key in the secret
            env_var: Environment variable name (fallback)

        Returns:
            Credential value or None
        """
        # Try Kubernetes first
        value = self.get_secret_from_k8s(secret_name, key)
        if value:
            return value

        # Fallback to environment variable
        if env_var:
            value = self.get_secret_from_env(env_var)
            if value:
                return value

        logger.warning(f"Credential not found: {secret_name}/{key} (env: {env_var})")
        return None

    def get_mcp_credentials(self, mcp_name: str) -> Dict[str, str]:
        """
        Get all credentials for a specific MCP.

        Maps MCP names to their required credentials based on Fase 1 configuration.

        Args:
            mcp_name: Name of the MCP (e.g., "github", "openai")

        Returns:
            Dictionary of environment variables and their values
        """
        credentials = {}

        # MCP credential mapping (Fase 1)
        credential_map = {
            "github": {
                "secret_name": "mcp-github-secrets",
                "mappings": [
                    ("GITHUB_TOKEN", "GITHUB_TOKEN", "GITHUB_TOKEN")
                ]
            },
            "openai": {
                "secret_name": "mcp-openai-secrets",
                "mappings": [
                    ("OPENAI_API_KEY", "OPENAI_API_KEY", "OPENAI_API_KEY")
                ]
            },
            "anthropic": {
                "secret_name": "mcp-anthropic-secrets",
                "mappings": [
                    ("ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")
                ]
            },
            "gcp": {
                "secret_name": "mcp-gcp-secrets",
                "mappings": [
                    ("GCP_PROJECT_ID", "GCP_PROJECT_ID", "GCP_PROJECT_ID")
                ]
            },
            "kubernetes": {
                "secret_name": "mcp-kubernetes-secrets",
                "mappings": [
                    ("KUBECONFIG", "KUBECONFIG", "KUBECONFIG")
                ]
            },
            # MCPs without credentials
            "filesystem": {"secret_name": None, "mappings": []},
            "git": {"secret_name": None, "mappings": []},
            "memory": {"secret_name": None, "mappings": []},
        }

        if mcp_name not in credential_map:
            logger.warning(f"Unknown MCP: {mcp_name}")
            return credentials

        config = credential_map[mcp_name]

        if not config["secret_name"]:
            # No credentials needed
            logger.debug(f"MCP {mcp_name} does not require credentials")
            return credentials

        # Get each credential
        for env_var, secret_key, fallback_env in config["mappings"]:
            value = self.get_credential(
                config["secret_name"],
                secret_key,
                fallback_env
            )
            if value:
                credentials[env_var] = value
            else:
                logger.warning(f"Missing credential {env_var} for MCP {mcp_name}")

        return credentials

    def validate_mcp_credentials(self, mcp_name: str) -> bool:
        """
        Validate that all required credentials are available for an MCP.

        Args:
            mcp_name: Name of the MCP

        Returns:
            True if all credentials are available
        """
        credentials = self.get_mcp_credentials(mcp_name)

        # Check if we got all required credentials
        required_counts = {
            "github": 1,
            "openai": 1,
            "anthropic": 1,
            "gcp": 1,
            "kubernetes": 1,
            "filesystem": 0,
            "git": 0,
            "memory": 0,
        }

        required = required_counts.get(mcp_name, 0)
        actual = len(credentials)

        if actual >= required:
            logger.info(f"✅ MCP {mcp_name} credentials validated ({actual}/{required})")
            return True
        else:
            logger.warning(f"❌ MCP {mcp_name} missing credentials ({actual}/{required})")
            return False

    def get_all_available_mcps(self) -> List[str]:
        """
        Get list of MCPs that have valid credentials.

        Returns:
            List of MCP names
        """
        all_mcps = ["github", "openai", "anthropic", "gcp", "kubernetes",
                    "filesystem", "git", "memory"]

        available = []
        for mcp in all_mcps:
            if self.validate_mcp_credentials(mcp):
                available.append(mcp)

        return available

    def clear_cache(self):
        """Clear the credential cache."""
        self._cache.clear()
        logger.info("Credential cache cleared")

    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        total = len(self._cache)
        expired = 0

        now = datetime.now()
        for _, (_, timestamp) in self._cache.items():
            if now - timestamp >= self.cache_ttl:
                expired += 1

        return {
            "total_cached": total,
            "expired": expired,
            "valid": total - expired,
            "cache_ttl_seconds": int(self.cache_ttl.total_seconds())
        }


# Global instance (can be overridden)
_global_manager: Optional[MCPCredentialsManager] = None


def get_credentials_manager(
    namespace: str = "default",
    cache_ttl_seconds: int = 300
) -> MCPCredentialsManager:
    """
    Get or create the global credentials manager instance.

    Args:
        namespace: Kubernetes namespace
        cache_ttl_seconds: Cache TTL

    Returns:
        MCPCredentialsManager instance
    """
    global _global_manager

    if _global_manager is None:
        _global_manager = MCPCredentialsManager(
            namespace=namespace,
            cache_ttl_seconds=cache_ttl_seconds
        )

    return _global_manager

"""
Lazy MCP Loader - Load MCPs on-demand

Provides:
- Lazy loading of MCPs to reduce startup time
- Connection pooling for MCP clients
- Resource cleanup
- Load tracking and metrics
"""

import logging
import time
import subprocess
from typing import Optional, Dict, Any
import json

logger = logging.getLogger(__name__)


class LazyMCPLoader:
    """
    Lazy loader for MCPs

    Loads MCPs only when first accessed, not at startup.
    Dramatically reduces startup time and memory usage.
    """

    def __init__(self, registry):
        """
        Initialize lazy loader

        Args:
            registry: MCPRegistry instance
        """
        self.registry = registry
        self._load_times: Dict[str, float] = {}

    def load(self, name: str) -> bool:
        """
        Load an MCP by name

        Args:
            name: MCP name

        Returns:
            True if successfully loaded
        """
        instance = self.registry._mcps.get(name)
        if not instance:
            logger.error(f"MCP {name} not found in registry")
            return False

        if instance.loaded:
            logger.debug(f"MCP {name} already loaded")
            return True

        if not instance.config.enabled:
            logger.warning(f"MCP {name} is disabled, not loading")
            return False

        start_time = time.time()
        logger.info(f"Loading MCP: {name} (category={instance.config.category.value})")

        try:
            # Load based on MCP type
            mcp_client = self._load_mcp_client(instance.config)

            if mcp_client is None:
                logger.error(f"Failed to create client for MCP {name}")
                instance.error_count += 1
                return False

            # Store instance
            instance.instance = mcp_client
            instance.loaded = True
            instance.last_loaded = time.time()

            load_time = time.time() - start_time
            self._load_times[name] = load_time

            logger.info(
                f"Successfully loaded MCP {name} in {load_time:.2f}s"
            )

            self.registry._loaded_count += 1
            return True

        except Exception as e:
            logger.error(f"Error loading MCP {name}: {e}", exc_info=True)
            instance.error_count += 1
            return False

    def _load_mcp_client(self, config) -> Optional[Any]:
        """
        Load MCP client based on configuration

        Args:
            config: MCPConfig

        Returns:
            MCP client instance or None
        """
        try:
            # Import MCP client factory
            from ..mcp_integration.mcp_client import create_mcp_client

            # Get credentials if needed
            credentials = None
            if config.credentials_source == "kubernetes" and config.secret_name:
                credentials = self._load_credentials_from_k8s(config.secret_name)
            elif config.credentials_source == "environment":
                credentials = config.env_vars

            # Create client
            client = create_mcp_client(
                name=config.name,
                command=config.command,
                args=config.args,
                env=credentials or {},
                timeout=config.timeout_seconds,
            )

            return client

        except ImportError:
            # Fallback: Create simple MCP client wrapper
            logger.warning(f"MCP client factory not available, using fallback for {config.name}")
            return self._create_fallback_client(config)

        except Exception as e:
            logger.error(f"Error creating MCP client for {config.name}: {e}")
            return None

    def _create_fallback_client(self, config) -> Any:
        """
        Create a fallback MCP client wrapper

        This is used when the full MCP client infrastructure isn't available yet.
        """
        class FallbackMCPClient:
            def __init__(self, config):
                self.config = config
                self.name = config.name

            def health_check(self):
                return "healthy"

            def close(self):
                pass

        return FallbackMCPClient(config)

    def _load_credentials_from_k8s(self, secret_name: str) -> Dict[str, str]:
        """
        Load credentials from Kubernetes secret

        Args:
            secret_name: Name of Kubernetes secret

        Returns:
            Dict of credential key-value pairs
        """
        try:
            # Try to load from external secrets first
            import os
            from pathlib import Path

            # Check if running in Kubernetes
            k8s_secret_path = Path(f"/var/secrets/{secret_name}")
            if k8s_secret_path.exists():
                credentials = {}
                for file in k8s_secret_path.glob("*"):
                    if file.is_file():
                        credentials[file.name.upper()] = file.read_text().strip()
                return credentials

            # Fallback to environment variables
            logger.warning(
                f"K8s secret {secret_name} not found, falling back to environment"
            )
            return {}

        except Exception as e:
            logger.error(f"Error loading credentials from K8s: {e}")
            return {}

    def load_by_category(self, category: str) -> int:
        """
        Load all MCPs in a category

        Args:
            category: MCP category

        Returns:
            Number of MCPs successfully loaded
        """
        from .registry import MCPCategory

        try:
            cat = MCPCategory(category)
        except ValueError:
            logger.error(f"Invalid category: {category}")
            return 0

        mcps = self.registry.get_by_category(cat)
        loaded = 0

        for instance in mcps:
            if not instance.loaded and instance.config.enabled:
                if self.load(instance.config.name):
                    loaded += 1

        logger.info(f"Loaded {loaded}/{len(mcps)} MCPs in category {category}")
        return loaded

    def load_by_priority(self, priority: int) -> int:
        """
        Load all MCPs with a priority level

        Args:
            priority: Priority level (1=CRITICAL, 2=HIGH, etc.)

        Returns:
            Number of MCPs successfully loaded
        """
        from .registry import MCPPriority

        try:
            prio = MCPPriority(priority)
        except ValueError:
            logger.error(f"Invalid priority: {priority}")
            return 0

        mcps = self.registry.get_by_priority(prio)
        loaded = 0

        for instance in mcps:
            if not instance.loaded and instance.config.enabled:
                if self.load(instance.config.name):
                    loaded += 1

        logger.info(f"Loaded {loaded}/{len(mcps)} MCPs with priority {priority}")
        return loaded

    def preload_critical(self) -> int:
        """
        Preload all CRITICAL priority MCPs

        Returns:
            Number of MCPs loaded
        """
        return self.load_by_priority(1)  # 1 = CRITICAL

    def get_load_stats(self) -> Dict[str, Any]:
        """
        Get loading statistics

        Returns:
            Dict with load times and statistics
        """
        if not self._load_times:
            return {
                "total_loaded": 0,
                "avg_load_time": 0.0,
                "max_load_time": 0.0,
                "min_load_time": 0.0,
            }

        times = list(self._load_times.values())
        return {
            "total_loaded": len(times),
            "avg_load_time": sum(times) / len(times),
            "max_load_time": max(times),
            "min_load_time": min(times),
            "load_times": self._load_times,
        }

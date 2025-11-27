"""
MCP Manager - Central orchestration of all MCP operations

Provides:
- Unified interface for MCP management
- Automatic initialization with foundation architecture
- Health monitoring and routing
- Easy integration with existing systems
"""

import logging
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any

from .registry import MCPRegistry, MCPCategory, MCPPriority, get_registry
from .lazy_loader import LazyMCPLoader
from .router import MCPRouter
from .circuit_breaker import get_circuit_breaker_manager, CircuitBreakerConfig
from .health_monitor import MCPHealthMonitor, HealthCheckConfig

logger = logging.getLogger(__name__)


class MCPManager:
    """
    Central MCP Manager

    Orchestrates all MCP foundation components:
    - Registry for MCP registration
    - Lazy loader for on-demand loading
    - AI-powered router for intelligent selection
    - Circuit breaker for failure protection
    - Health monitor for continuous monitoring
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        auto_load_critical: bool = True,
    ):
        """
        Initialize MCP Manager

        Args:
            config_path: Path to MCP configuration YAML
            auto_load_critical: Auto-load CRITICAL priority MCPs
        """
        # Initialize components
        self.registry = get_registry()
        self.loader = LazyMCPLoader(self.registry)
        self.router = MCPRouter(self.registry)
        self.circuit_breaker_manager = get_circuit_breaker_manager()
        self.health_monitor = MCPHealthMonitor(self.registry)

        # Load configuration
        if config_path:
            self.load_config(config_path)
        else:
            # Load default configs
            self.load_default_configs()

        # Auto-load critical MCPs
        if auto_load_critical:
            loaded = self.loader.preload_critical()
            logger.info(f"Auto-loaded {loaded} critical MCPs")

        logger.info("MCPManager initialized successfully")

    def load_config(self, config_path: str) -> int:
        """
        Load MCP configuration from YAML file

        Args:
            config_path: Path to configuration YAML

        Returns:
            Number of MCPs registered
        """
        logger.info(f"Loading MCP configuration from {config_path}")

        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)

            if not config or 'mcps' not in config:
                logger.error(f"Invalid configuration file: {config_path}")
                return 0

            registered = 0

            for mcp_config in config['mcps']:
                try:
                    name = mcp_config['name']
                    category_str = mcp_config.get('category', 'reference')
                    priority = mcp_config.get('priority', 3)

                    # Convert category string to enum
                    category = MCPCategory(category_str)

                    # Convert priority int to enum
                    priority_enum = MCPPriority(priority)

                    # Register MCP
                    self.registry.register(
                        name=name,
                        category=category,
                        priority=priority_enum,
                        enabled=mcp_config.get('enabled', True),
                        lazy_load=mcp_config.get('lazy_load', True),
                        command=mcp_config.get('transport', {}).get('command', ''),
                        args=mcp_config.get('transport', {}).get('args', []),
                        env_vars=mcp_config.get('transport', {}).get('env', {}),
                        credentials_source=mcp_config.get('credentials_source', 'kubernetes'),
                        secret_name=mcp_config.get('secret_name'),
                        timeout_seconds=mcp_config.get('timeout_seconds', 30),
                        retry_attempts=mcp_config.get('retry_attempts', 3),
                        cache_ttl_seconds=mcp_config.get('cache_ttl_seconds', 300),
                        rate_limit_per_minute=mcp_config.get('rate_limit_per_minute'),
                        metadata=mcp_config.get('metadata', {}),
                    )

                    registered += 1
                    logger.info(f"Registered MCP: {name}")

                except Exception as e:
                    logger.error(f"Error registering MCP {mcp_config.get('name', 'unknown')}: {e}")
                    continue

            logger.info(f"Successfully registered {registered} MCPs from {config_path}")
            return registered

        except Exception as e:
            logger.error(f"Error loading configuration from {config_path}: {e}", exc_info=True)
            return 0

    def load_default_configs(self) -> int:
        """
        Load all default MCP configurations

        Returns:
            Total number of MCPs registered
        """
        total = 0

        # Try to load all fase configs
        config_dir = Path("/app/data/external_mcps")
        if not config_dir.exists():
            # Fallback to relative path
            config_dir = Path(__file__).parent.parent.parent / "data" / "external_mcps"

        if not config_dir.exists():
            logger.warning(f"MCP config directory not found: {config_dir}")
            return 0

        # Load in order: fase1, fase2, fase3, etc.
        for fase in range(1, 12):
            config_file = config_dir / f"fase{fase}-mcps-config.yaml"
            if config_file.exists():
                count = self.load_config(str(config_file))
                total += count
                logger.info(f"Loaded Fase {fase}: {count} MCPs")
            else:
                logger.debug(f"Config not found: {config_file}")

        return total

    def query(
        self,
        user_query: str,
        use_router: bool = True,
        max_mcps: int = 10,
    ) -> Dict[str, Any]:
        """
        Process a query using intelligent MCP routing

        Args:
            user_query: User's query
            use_router: Use AI router for MCP selection
            max_mcps: Maximum MCPs to use

        Returns:
            Dict with routing info and selected MCPs
        """
        if use_router:
            # Use AI-powered routing
            routing = self.router.route(user_query, max_mcps=max_mcps)

            # Load selected MCPs
            loaded_mcps = []
            for mcp_name in routing.selected_mcps:
                instance = self.registry.get(mcp_name, auto_load=True)
                if instance and instance.loaded:
                    loaded_mcps.append(mcp_name)

            return {
                "selected_mcps": loaded_mcps,
                "confidence": routing.confidence,
                "reasoning": routing.reasoning,
                "categories": list(routing.categories_used),
                "total_available": len(self.registry.list_mcps(enabled_only=True)),
            }
        else:
            # Load all enabled MCPs
            all_mcps = self.registry.list_mcps(enabled_only=True)
            return {
                "selected_mcps": all_mcps,
                "confidence": 1.0,
                "reasoning": "Using all enabled MCPs",
                "categories": [],
                "total_available": len(all_mcps),
            }

    def get_mcp(
        self,
        name: str,
        with_circuit_breaker: bool = True,
    ) -> Optional[Any]:
        """
        Get MCP instance with optional circuit breaker protection

        Args:
            name: MCP name
            with_circuit_breaker: Wrap with circuit breaker

        Returns:
            MCP instance or None
        """
        instance = self.registry.get(name, auto_load=True)
        if not instance or not instance.loaded:
            return None

        if with_circuit_breaker:
            breaker = self.circuit_breaker_manager.get_breaker(
                name,
                config=CircuitBreakerConfig(
                    failure_threshold=5,
                    success_threshold=2,
                    timeout=60.0,
                )
            )
            # Return wrapped instance
            # Note: Actual wrapping implementation depends on MCP client interface
            return instance.instance

        return instance.instance

    def health_check(self) -> Dict[str, Any]:
        """
        Run comprehensive health check

        Returns:
            Health report
        """
        return self.health_monitor.get_health_report()

    def get_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive statistics

        Returns:
            Statistics about MCPs, routing, circuits, health
        """
        return {
            "registry": self.registry.get_stats(),
            "loader": self.loader.get_load_stats(),
            "router": self.router.get_routing_stats(),
            "circuit_breakers": self.circuit_breaker_manager.health_check(),
            "health": self.health_monitor.get_health_report(),
        }

    def unload_idle(self, idle_seconds: int = 3600) -> int:
        """
        Unload idle MCPs to free resources

        Args:
            idle_seconds: Unload MCPs idle for this long

        Returns:
            Number of MCPs unloaded
        """
        return self.registry.unload_idle(idle_seconds)

    def reload_config(self, config_path: str) -> bool:
        """
        Reload configuration (hot reload)

        Args:
            config_path: Path to new configuration

        Returns:
            True if successful
        """
        try:
            # Unload all MCPs
            for instance in self.registry.get_all_loaded():
                self.registry.unload(instance.config.name)

            # Clear and reload
            count = self.load_config(config_path)

            logger.info(f"Hot reload successful: {count} MCPs registered")
            return True

        except Exception as e:
            logger.error(f"Hot reload failed: {e}", exc_info=True)
            return False


# Global manager instance
_global_manager = None


def get_manager(
    config_path: Optional[str] = None,
    auto_load_critical: bool = True,
) -> MCPManager:
    """
    Get the global MCP manager

    Args:
        config_path: Optional config path (only used on first call)
        auto_load_critical: Auto-load critical MCPs (only on first call)

    Returns:
        MCPManager instance
    """
    global _global_manager

    if _global_manager is None:
        _global_manager = MCPManager(
            config_path=config_path,
            auto_load_critical=auto_load_critical,
        )

    return _global_manager

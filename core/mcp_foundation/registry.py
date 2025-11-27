"""
MCP Registry - Central registration and management of all MCPs

Provides:
- MCP registration with lazy loading support
- Category-based MCP discovery
- Health check aggregation
- Configuration management
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import time

logger = logging.getLogger(__name__)


class MCPCategory(str, Enum):
    """MCP Categories for organization"""
    GOOGLE_WORKSPACE = "google_workspace"
    COMMUNICATION = "communication"
    DATABASE = "database"
    CLOUD = "cloud"
    DEVELOPMENT = "development"
    MONITORING = "monitoring"
    PROJECT_MANAGEMENT = "project_management"
    ANALYTICS = "analytics"
    ECOMMERCE = "ecommerce"
    CRM = "crm"
    SOCIAL_MEDIA = "social_media"
    AUTOMATION = "automation"
    REFERENCE = "reference"
    AI_ML = "ai_ml"


class MCPPriority(int, Enum):
    """MCP Priority levels"""
    CRITICAL = 1  # Must be available
    HIGH = 2      # Should be available
    MEDIUM = 3    # Nice to have
    LOW = 4       # Optional


@dataclass
class MCPConfig:
    """Configuration for a single MCP"""
    name: str
    category: MCPCategory
    priority: MCPPriority
    enabled: bool = True
    lazy_load: bool = True
    transport_type: str = "stdio"
    command: str = ""
    args: List[str] = field(default_factory=list)
    env_vars: Dict[str, str] = field(default_factory=dict)
    credentials_source: str = "kubernetes"
    secret_name: Optional[str] = None
    timeout_seconds: int = 30
    retry_attempts: int = 3
    cache_ttl_seconds: int = 300
    rate_limit_per_minute: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPInstance:
    """Runtime instance of an MCP"""
    config: MCPConfig
    instance: Optional[Any] = None  # Actual MCP client instance
    loaded: bool = False
    last_loaded: Optional[float] = None
    last_used: Optional[float] = None
    error_count: int = 0
    success_count: int = 0
    total_calls: int = 0
    avg_response_time: float = 0.0
    health_status: str = "unknown"


class MCPRegistry:
    """
    Central registry for all MCPs

    Responsibilities:
    - Register MCPs with configurations
    - Lazy load MCPs on first use
    - Track MCP usage and health
    - Provide category-based discovery
    """

    def __init__(self):
        self._mcps: Dict[str, MCPInstance] = {}
        self._categories: Dict[MCPCategory, List[str]] = {}
        self._priorities: Dict[MCPPriority, List[str]] = {}
        self._loaded_count: int = 0
        logger.info("MCPRegistry initialized")

    def register(
        self,
        name: str,
        category: MCPCategory,
        priority: MCPPriority,
        **kwargs
    ) -> None:
        """
        Register an MCP with the registry

        Args:
            name: MCP name (unique identifier)
            category: MCP category
            priority: MCP priority level
            **kwargs: Additional configuration options
        """
        if name in self._mcps:
            logger.warning(f"MCP {name} already registered, updating configuration")

        config = MCPConfig(
            name=name,
            category=category,
            priority=priority,
            **kwargs
        )

        instance = MCPInstance(config=config)
        self._mcps[name] = instance

        # Update category index
        if category not in self._categories:
            self._categories[category] = []
        if name not in self._categories[category]:
            self._categories[category].append(name)

        # Update priority index
        if priority not in self._priorities:
            self._priorities[priority] = []
        if name not in self._priorities[priority]:
            self._priorities[priority].append(name)

        logger.info(
            f"Registered MCP: {name} "
            f"(category={category.value}, priority={priority.value}, "
            f"lazy_load={config.lazy_load})"
        )

    def get(self, name: str, auto_load: bool = True) -> Optional[MCPInstance]:
        """
        Get MCP instance by name

        Args:
            name: MCP name
            auto_load: If True and MCP not loaded, load it now

        Returns:
            MCPInstance or None if not found
        """
        if name not in self._mcps:
            logger.warning(f"MCP {name} not found in registry")
            return None

        instance = self._mcps[name]

        # Auto-load if requested and not yet loaded
        if auto_load and not instance.loaded and instance.config.lazy_load:
            from .lazy_loader import LazyMCPLoader
            loader = LazyMCPLoader(self)
            success = loader.load(name)
            if not success:
                logger.error(f"Failed to auto-load MCP {name}")
                return None

        # Update last used timestamp
        instance.last_used = time.time()

        return instance

    def get_by_category(self, category: MCPCategory) -> List[MCPInstance]:
        """Get all MCPs in a category"""
        mcp_names = self._categories.get(category, [])
        return [self._mcps[name] for name in mcp_names if name in self._mcps]

    def get_by_priority(self, priority: MCPPriority) -> List[MCPInstance]:
        """Get all MCPs with a priority level"""
        mcp_names = self._priorities.get(priority, [])
        return [self._mcps[name] for name in mcp_names if name in self._mcps]

    def get_all_loaded(self) -> List[MCPInstance]:
        """Get all currently loaded MCPs"""
        return [mcp for mcp in self._mcps.values() if mcp.loaded]

    def get_all_enabled(self) -> List[MCPInstance]:
        """Get all enabled MCPs (regardless of loaded status)"""
        return [mcp for mcp in self._mcps.values() if mcp.config.enabled]

    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics"""
        total = len(self._mcps)
        loaded = len(self.get_all_loaded())
        enabled = len(self.get_all_enabled())

        category_counts = {
            cat.value: len(names)
            for cat, names in self._categories.items()
        }

        priority_counts = {
            f"priority_{prio.value}": len(names)
            for prio, names in self._priorities.items()
        }

        return {
            "total_mcps": total,
            "loaded_mcps": loaded,
            "enabled_mcps": enabled,
            "load_percentage": (loaded / total * 100) if total > 0 else 0,
            "categories": category_counts,
            "priorities": priority_counts,
        }

    def unload(self, name: str) -> bool:
        """
        Unload an MCP to free resources

        Args:
            name: MCP name

        Returns:
            True if successfully unloaded
        """
        if name not in self._mcps:
            return False

        instance = self._mcps[name]
        if not instance.loaded:
            return True

        # Close/cleanup MCP instance
        if instance.instance and hasattr(instance.instance, 'close'):
            try:
                instance.instance.close()
            except Exception as e:
                logger.error(f"Error closing MCP {name}: {e}")

        instance.instance = None
        instance.loaded = False
        self._loaded_count -= 1

        logger.info(f"Unloaded MCP: {name}")
        return True

    def unload_idle(self, idle_seconds: int = 3600) -> int:
        """
        Unload MCPs that haven't been used recently

        Args:
            idle_seconds: Unload MCPs idle for this many seconds

        Returns:
            Number of MCPs unloaded
        """
        current_time = time.time()
        unloaded = 0

        for instance in self.get_all_loaded():
            if instance.last_used is None:
                continue

            idle_time = current_time - instance.last_used
            if idle_time > idle_seconds:
                if self.unload(instance.config.name):
                    unloaded += 1
                    logger.info(
                        f"Unloaded idle MCP {instance.config.name} "
                        f"(idle for {idle_time:.0f}s)"
                    )

        return unloaded

    def health_check_all(self) -> Dict[str, str]:
        """
        Check health of all loaded MCPs

        Returns:
            Dict mapping MCP name to health status
        """
        results = {}

        for instance in self.get_all_loaded():
            try:
                if instance.instance and hasattr(instance.instance, 'health_check'):
                    status = instance.instance.health_check()
                    instance.health_status = status
                else:
                    # If no health check method, assume healthy if loaded
                    instance.health_status = "healthy"

                results[instance.config.name] = instance.health_status
            except Exception as e:
                logger.error(f"Health check failed for {instance.config.name}: {e}")
                instance.health_status = "unhealthy"
                results[instance.config.name] = "unhealthy"

        return results

    def disable(self, name: str) -> bool:
        """Disable an MCP"""
        if name not in self._mcps:
            return False

        self._mcps[name].config.enabled = False
        self.unload(name)
        logger.info(f"Disabled MCP: {name}")
        return True

    def enable(self, name: str) -> bool:
        """Enable an MCP"""
        if name not in self._mcps:
            return False

        self._mcps[name].config.enabled = True
        logger.info(f"Enabled MCP: {name}")
        return True

    def list_mcps(
        self,
        category: Optional[MCPCategory] = None,
        priority: Optional[MCPPriority] = None,
        loaded_only: bool = False,
        enabled_only: bool = False,
    ) -> List[str]:
        """
        List MCP names with optional filters

        Args:
            category: Filter by category
            priority: Filter by priority
            loaded_only: Only return loaded MCPs
            enabled_only: Only return enabled MCPs

        Returns:
            List of MCP names
        """
        mcps = self._mcps.values()

        if category:
            mcps = [m for m in mcps if m.config.category == category]

        if priority:
            mcps = [m for m in mcps if m.config.priority == priority]

        if loaded_only:
            mcps = [m for m in mcps if m.loaded]

        if enabled_only:
            mcps = [m for m in mcps if m.config.enabled]

        return [m.config.name for m in mcps]


# Global registry instance
_global_registry = None


def get_registry() -> MCPRegistry:
    """Get the global MCP registry"""
    global _global_registry
    if _global_registry is None:
        _global_registry = MCPRegistry()
    return _global_registry

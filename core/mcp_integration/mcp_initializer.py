"""
MCP Initializer - Auto-discovery and initialization of external MCPs

Loads MCP configuration from YAML and initializes them with proper credentials.
"""

import os
import logging
import yaml
from typing import Dict, List, Optional
from pathlib import Path

from .mcp_credentials_manager import MCPCredentialsManager, get_credentials_manager
from .mcp_registry import MCPRegistry, ExternalMCP
from .mcp_connection_pool import MCPConnectionPool

logger = logging.getLogger(__name__)


class MCPInitializer:
    """
    Initializes external MCPs from configuration files.

    Features:
    - Auto-discovery from YAML files
    - Credential injection from Kubernetes secrets
    - Validation of MCP availability
    - Health checks
    """

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        credentials_manager: Optional[MCPCredentialsManager] = None
    ):
        """
        Initialize MCP Initializer.

        Args:
            config_dir: Directory containing MCP configuration files
            credentials_manager: Credentials manager instance
        """
        if config_dir is None:
            # Default to data/external_mcps in project root
            project_root = Path(__file__).parent.parent.parent
            config_dir = project_root / "data" / "external_mcps"

        self.config_dir = Path(config_dir)
        self.credentials_manager = credentials_manager or get_credentials_manager()

        logger.info(f"MCPInitializer initialized (config_dir={self.config_dir})")

    def load_config_file(self, config_file: Path) -> Dict:
        """
        Load configuration from a YAML file.

        Args:
            config_file: Path to YAML config file

        Returns:
            Configuration dictionary
        """
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
                logger.info(f"Loaded config from {config_file}")
                return config
        except Exception as e:
            logger.error(f"Error loading config {config_file}: {e}")
            return {}

    def discover_mcps(self) -> List[Dict]:
        """
        Discover all MCP configurations in config_dir.

        Returns:
            List of MCP configurations
        """
        all_mcps = []

        if not self.config_dir.exists():
            logger.warning(f"Config directory does not exist: {self.config_dir}")
            return all_mcps

        # Find all YAML files
        yaml_files = list(self.config_dir.glob("*.yaml")) + list(self.config_dir.glob("*.yml"))

        for yaml_file in yaml_files:
            config = self.load_config_file(yaml_file)

            if not config:
                continue

            # Extract MCPs from config
            if "mcps" in config:
                mcps_list = config["mcps"]
                logger.info(f"Found {len(mcps_list)} MCPs in {yaml_file.name}")
                all_mcps.extend(mcps_list)
            elif "name" in config:
                # Single MCP config
                logger.info(f"Found 1 MCP in {yaml_file.name}")
                all_mcps.append(config)

        logger.info(f"Discovered {len(all_mcps)} MCPs total")
        return all_mcps

    def validate_mcp_config(self, mcp_config: Dict) -> bool:
        """
        Validate an MCP configuration.

        Args:
            mcp_config: MCP configuration dict

        Returns:
            True if valid
        """
        required_fields = ["name", "enabled", "transport"]

        for field in required_fields:
            if field not in mcp_config:
                logger.warning(f"MCP config missing required field: {field}")
                return False

        return True

    def inject_credentials(self, mcp_config: Dict) -> Dict[str, str]:
        """
        Inject credentials for an MCP.

        Args:
            mcp_config: MCP configuration

        Returns:
            Environment variables dictionary
        """
        mcp_name = mcp_config["name"]
        credentials_source = mcp_config.get("credentials_source", "none")

        if credentials_source == "none":
            logger.debug(f"MCP {mcp_name} does not require credentials")
            return {}

        if credentials_source == "kubernetes":
            # Get credentials from K8s secrets via credentials manager
            credentials = self.credentials_manager.get_mcp_credentials(mcp_name)
            logger.info(f"Injected {len(credentials)} credentials for MCP {mcp_name}")
            return credentials

        elif credentials_source == "environment":
            # Already in environment, no injection needed
            logger.debug(f"MCP {mcp_name} uses environment variables")
            return {}

        else:
            logger.warning(f"Unknown credentials source for {mcp_name}: {credentials_source}")
            return {}

    def create_external_mcp(self, mcp_config: Dict) -> Optional[ExternalMCP]:
        """
        Create an ExternalMCP instance from configuration.

        Args:
            mcp_config: MCP configuration

        Returns:
            ExternalMCP instance or None
        """
        if not self.validate_mcp_config(mcp_config):
            return None

        if not mcp_config.get("enabled", False):
            logger.debug(f"MCP {mcp_config['name']} is disabled")
            return None

        # Inject credentials
        env_vars = self.inject_credentials(mcp_config)

        # Prepare connection config with environment variables
        connection_config = mcp_config["transport"].copy()
        if env_vars:
            connection_config["env"] = env_vars

        # Create ExternalMCP using correct parameters
        try:
            mcp = ExternalMCP(
                name=mcp_config["name"],
                category=mcp_config.get("category", "unknown"),
                transport=mcp_config["transport"].get("type", "stdio"),
                connection=connection_config,
                capabilities=mcp_config.get("capabilities", []),
                description=mcp_config.get("description", ""),
                tags=mcp_config.get("tags", []),
                priority=mcp_config.get("priority", 50)
            )

            logger.info(f"✅ Created ExternalMCP: {mcp.name}")
            return mcp

        except Exception as e:
            logger.error(f"Error creating ExternalMCP {mcp_config['name']}: {e}")
            return None

    def initialize_mcps(self, registry: MCPRegistry) -> int:
        """
        Discover and initialize all MCPs, registering them in the registry.

        Args:
            registry: MCPRegistry to register MCPs in

        Returns:
            Number of MCPs initialized
        """
        logger.info("🚀 Initializing MCPs...")

        # Discover MCPs
        mcp_configs = self.discover_mcps()

        if not mcp_configs:
            logger.warning("No MCP configurations found")
            return 0

        # Initialize each MCP
        initialized_count = 0

        for mcp_config in mcp_configs:
            mcp = self.create_external_mcp(mcp_config)

            if mcp:
                # Register in registry
                registry.register_mcp(mcp)
                initialized_count += 1

        logger.info(f"✅ Initialized {initialized_count}/{len(mcp_configs)} MCPs")

        return initialized_count

    def get_available_mcps(self) -> List[str]:
        """
        Get list of MCPs that are available (have valid credentials).

        Returns:
            List of MCP names
        """
        return self.credentials_manager.get_all_available_mcps()

    def health_check_all(self, registry: MCPRegistry) -> Dict[str, bool]:
        """
        Perform health checks on all registered MCPs.

        Args:
            registry: MCPRegistry instance

        Returns:
            Dictionary of {mcp_name: is_healthy}
        """
        results = {}

        # Get all MCP names from registry
        all_mcps = list(registry.mcps.keys())

        for mcp_name in all_mcps:
            mcp = registry.get_mcp(mcp_name)

            if not mcp:
                results[mcp_name] = False
                continue

            # TODO: Implement actual health check
            # For now, just check if credentials are available
            has_credentials = self.credentials_manager.validate_mcp_credentials(mcp_name)
            results[mcp_name] = has_credentials

        return results


def initialize_fase1_mcps() -> tuple[MCPRegistry, MCPCredentialsManager, int]:
    """
    Quick initialization of Fase 1 MCPs.

    Returns:
        Tuple of (registry, credentials_manager, count)
    """
    logger.info("🚀 Initializing Fase 1 MCPs...")

    # Create instances
    credentials_manager = get_credentials_manager()
    registry = MCPRegistry()
    initializer = MCPInitializer(credentials_manager=credentials_manager)

    # Initialize MCPs
    count = initializer.initialize_mcps(registry)

    logger.info(f"✅ Fase 1 initialization complete: {count} MCPs")

    return registry, credentials_manager, count

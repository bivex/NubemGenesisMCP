"""
Meta-MCP Orchestrator - MCP Registry Module

Manages external MCP servers similar to how PersonaRegistry manages personas.
Loads MCP definitions from YAML files, generates embeddings for semantic search,
and provides discovery and filtering capabilities.
"""

import os
import yaml
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ExternalMCP:
    """
    Represents an external MCP server definition.
    Similar to Persona but for external MCP servers.
    """
    name: str
    category: str
    transport: str  # 'stdio', 'http', 'sse'
    connection: Dict[str, Any]  # Connection configuration
    capabilities: List[str]
    description: str

    # Optional fields
    tags: List[str] = field(default_factory=list)
    priority: int = 50  # 0-100, higher = more important
    health_check_interval: int = 60  # seconds
    timeout: int = 30  # seconds
    retry_attempts: int = 3
    circuit_breaker_threshold: int = 5  # failures before opening circuit

    # Runtime fields
    embedding: Optional[np.ndarray] = None
    health_status: str = "unknown"  # 'healthy', 'unhealthy', 'unknown'
    last_health_check: Optional[datetime] = None
    consecutive_failures: int = 0

    # Metadata
    version: str = "1.0.0"
    author: str = ""
    documentation_url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (for serialization)"""
        return {
            'name': self.name,
            'category': self.category,
            'transport': self.transport,
            'connection': self.connection,
            'capabilities': self.capabilities,
            'description': self.description,
            'tags': self.tags,
            'priority': self.priority,
            'health_check_interval': self.health_check_interval,
            'timeout': self.timeout,
            'retry_attempts': self.retry_attempts,
            'circuit_breaker_threshold': self.circuit_breaker_threshold,
            'health_status': self.health_status,
            'last_health_check': self.last_health_check.isoformat() if self.last_health_check else None,
            'consecutive_failures': self.consecutive_failures,
            'version': self.version,
            'author': self.author,
            'documentation_url': self.documentation_url
        }

    def get_searchable_text(self) -> str:
        """
        Get text for semantic search embedding.
        Combines name, description, capabilities, and tags.
        """
        parts = [
            self.name,
            self.description,
            f"Category: {self.category}",
            f"Capabilities: {', '.join(self.capabilities)}",
            f"Tags: {', '.join(self.tags)}"
        ]
        return " | ".join(parts)

    def is_healthy(self) -> bool:
        """Check if MCP is healthy and available"""
        return self.health_status == "healthy" and self.consecutive_failures < self.circuit_breaker_threshold


class MCPRegistry:
    """
    Registry for external MCP servers.
    Similar to PersonaRegistry but manages external MCP connections.
    """

    def __init__(self, yaml_dir: str = None, embedding_generator=None):
        """
        Initialize the MCP Registry.

        Args:
            yaml_dir: Directory containing MCP YAML definitions
            embedding_generator: Function to generate embeddings (should accept text and return np.ndarray)
        """
        self.yaml_dir = yaml_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data/external_mcps"
        )
        self.embedding_generator = embedding_generator

        self.mcps: Dict[str, ExternalMCP] = {}
        self.embeddings: Dict[str, np.ndarray] = {}
        self.categories: Set[str] = set()
        self.capabilities: Set[str] = set()

        self._loaded = False

        logger.info(f"MCPRegistry initialized with yaml_dir: {self.yaml_dir}")

    def load_external_mcps(self, force_reload: bool = False) -> int:
        """
        Load MCP definitions from YAML files.
        Similar to PersonaRegistry.load_external_personas()

        Args:
            force_reload: If True, reload even if already loaded

        Returns:
            Number of MCPs loaded
        """
        if self._loaded and not force_reload:
            logger.info("MCPs already loaded, skipping reload")
            return len(self.mcps)

        if not os.path.exists(self.yaml_dir):
            logger.warning(f"MCP directory not found: {self.yaml_dir}")
            os.makedirs(self.yaml_dir, exist_ok=True)
            return 0

        loaded_count = 0
        yaml_files = list(Path(self.yaml_dir).glob("*.yaml")) + list(Path(self.yaml_dir).glob("*.yml"))

        logger.info(f"Found {len(yaml_files)} MCP YAML files in {self.yaml_dir}")

        for yaml_file in yaml_files:
            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)

                if not config:
                    logger.warning(f"Empty YAML file: {yaml_file}")
                    continue

                # Support two formats:
                # 1. Single MCP per file (old format)
                # 2. Array of MCPs under 'mcps' key (new format)
                mcp_configs = []

                if 'mcps' in config and isinstance(config['mcps'], list):
                    # New format: multiple MCPs in one file
                    mcp_configs = [m for m in config['mcps'] if m.get('enabled', True)]
                    logger.info(f"Found {len(mcp_configs)} enabled MCPs in {yaml_file.name}")
                else:
                    # Old format: single MCP per file
                    mcp_configs = [config]

                # Load each MCP
                for mcp_config in mcp_configs:
                    mcp = self._create_mcp_from_config(mcp_config, yaml_file.name)

                    if mcp:
                        self.register_mcp(mcp)
                        loaded_count += 1
                        logger.info(f"✅ Loaded MCP: {mcp.name} from {yaml_file.name}")

            except Exception as e:
                logger.error(f"❌ Error loading MCP from {yaml_file}: {e}")
                continue

        self._loaded = True
        logger.info(f"Loaded {loaded_count} MCPs successfully")

        # Generate embeddings if embedding_generator provided
        if self.embedding_generator and loaded_count > 0:
            self._generate_embeddings()

        return loaded_count

    def _create_mcp_from_config(self, config: Dict[str, Any], filename: str) -> Optional[ExternalMCP]:
        """
        Create ExternalMCP object from YAML configuration.

        Args:
            config: YAML configuration dictionary
            filename: Source filename (for error reporting)

        Returns:
            ExternalMCP instance or None if invalid
        """
        # Transform config to expected format
        # Support both old format (transport=str, connection=dict)
        # and new format (transport=dict with type, command, args)

        transport_value = config.get('transport')
        connection_value = config.get('connection')

        if isinstance(transport_value, dict):
            # New format: transport is a dict with type, command, args
            transport_type = transport_value.get('type', 'stdio')
            connection_value = {
                'command': transport_value.get('command'),
                'args': transport_value.get('args', []),
                **{k: v for k, v in transport_value.items() if k not in ['type', 'command', 'args']}
            }
        elif isinstance(transport_value, str):
            # Old format: transport is string, connection is separate
            transport_type = transport_value
            if not connection_value:
                logger.error(f"Missing 'connection' field in {filename}")
                return None
        else:
            logger.error(f"Missing or invalid 'transport' field in {filename}")
            return None

        # Check required fields (adjusted for new format)
        required_base_fields = ['name', 'category', 'capabilities', 'description']
        missing_fields = [field for field in required_base_fields if field not in config]
        if missing_fields:
            logger.error(f"Missing required fields in {filename}: {missing_fields}")
            return None

        # Validate transport type
        valid_transports = ['stdio', 'http', 'sse']
        if transport_type not in valid_transports:
            logger.error(f"Invalid transport '{transport_type}' in {filename}. Must be one of: {valid_transports}")
            return None

        try:
            mcp = ExternalMCP(
                name=config['name'],
                category=config['category'],
                transport=transport_type,
                connection=connection_value,
                capabilities=config['capabilities'],
                description=config['description'],
                tags=config.get('tags', []),
                priority=config.get('priority', 50),
                health_check_interval=config.get('health_check_interval', 60),
                timeout=config.get('timeout', 30),
                retry_attempts=config.get('retry_attempts', 3),
                circuit_breaker_threshold=config.get('circuit_breaker_threshold', 5),
                version=config.get('metadata', {}).get('version', '1.0.0'),
                author=config.get('metadata', {}).get('author', ''),
                documentation_url=config.get('metadata', {}).get('docs_url', '')
            )
            return mcp

        except Exception as e:
            logger.error(f"Error creating MCP from {filename}: {e}")
            logger.exception(e)
            return None

    def register_mcp(self, mcp: ExternalMCP) -> bool:
        """
        Register an MCP in the registry.

        Args:
            mcp: ExternalMCP instance

        Returns:
            True if registered successfully
        """
        if mcp.name in self.mcps:
            logger.warning(f"MCP '{mcp.name}' already registered, overwriting")

        self.mcps[mcp.name] = mcp
        self.categories.add(mcp.category)
        self.capabilities.update(mcp.capabilities)

        logger.debug(f"Registered MCP: {mcp.name} (category: {mcp.category}, transport: {mcp.transport})")
        return True

    def _generate_embeddings(self):
        """Generate embeddings for all MCPs using the embedding_generator"""
        if not self.embedding_generator:
            logger.warning("No embedding generator provided, skipping embeddings")
            return

        logger.info(f"Generating embeddings for {len(self.mcps)} MCPs...")

        for name, mcp in self.mcps.items():
            try:
                searchable_text = mcp.get_searchable_text()
                embedding = self.embedding_generator(searchable_text)

                if isinstance(embedding, np.ndarray):
                    mcp.embedding = embedding
                    self.embeddings[name] = embedding
                else:
                    logger.warning(f"Invalid embedding type for {name}: {type(embedding)}")

            except Exception as e:
                logger.error(f"Error generating embedding for {name}: {e}")

        logger.info(f"Generated {len(self.embeddings)} embeddings")

    def get_mcp(self, name: str) -> Optional[ExternalMCP]:
        """Get MCP by name"""
        return self.mcps.get(name)

    def get_mcps_by_category(self, category: str) -> List[ExternalMCP]:
        """Get all MCPs in a specific category"""
        return [mcp for mcp in self.mcps.values() if mcp.category == category]

    def get_mcps_by_capability(self, capability: str) -> List[ExternalMCP]:
        """Get all MCPs that have a specific capability"""
        return [mcp for mcp in self.mcps.values() if capability in mcp.capabilities]

    def get_mcps_by_transport(self, transport: str) -> List[ExternalMCP]:
        """Get all MCPs using a specific transport"""
        return [mcp for mcp in self.mcps.values() if mcp.transport == transport]

    def get_healthy_mcps(self) -> List[ExternalMCP]:
        """Get all healthy MCPs (circuit breaker not open)"""
        return [mcp for mcp in self.mcps.values() if mcp.is_healthy()]

    def get_all_categories(self) -> List[str]:
        """Get list of all categories"""
        return sorted(list(self.categories))

    def get_all_capabilities(self) -> List[str]:
        """Get list of all capabilities across all MCPs"""
        return sorted(list(self.capabilities))

    def search_mcps(self, query: str, top_k: int = 5, filter_healthy: bool = True) -> List[tuple[ExternalMCP, float]]:
        """
        Search MCPs using semantic similarity (if embeddings available).

        Args:
            query: Search query text
            top_k: Number of top results to return
            filter_healthy: Only return healthy MCPs

        Returns:
            List of (MCP, similarity_score) tuples
        """
        if not self.embedding_generator or not self.embeddings:
            logger.warning("No embeddings available, returning all MCPs")
            mcps = list(self.mcps.values())
            if filter_healthy:
                mcps = [mcp for mcp in mcps if mcp.is_healthy()]
            return [(mcp, 1.0) for mcp in mcps[:top_k]]

        try:
            # Generate embedding for query
            query_embedding = self.embedding_generator(query)

            if not isinstance(query_embedding, np.ndarray):
                logger.error(f"Invalid query embedding type: {type(query_embedding)}")
                return []

            # Calculate similarities
            similarities = []
            for name, mcp in self.mcps.items():
                if filter_healthy and not mcp.is_healthy():
                    continue

                if mcp.embedding is not None:
                    # Cosine similarity
                    similarity = np.dot(query_embedding, mcp.embedding) / (
                        np.linalg.norm(query_embedding) * np.linalg.norm(mcp.embedding)
                    )
                    similarities.append((mcp, float(similarity)))

            # Sort by similarity (descending)
            similarities.sort(key=lambda x: x[1], reverse=True)

            return similarities[:top_k]

        except Exception as e:
            logger.error(f"Error in semantic search: {e}")
            return []

    def update_health_status(self, name: str, is_healthy: bool):
        """
        Update health status of an MCP.

        Args:
            name: MCP name
            is_healthy: True if healthy, False if unhealthy
        """
        mcp = self.mcps.get(name)
        if not mcp:
            logger.warning(f"MCP '{name}' not found in registry")
            return

        mcp.last_health_check = datetime.now()

        if is_healthy:
            mcp.health_status = "healthy"
            mcp.consecutive_failures = 0
        else:
            mcp.health_status = "unhealthy"
            mcp.consecutive_failures += 1

        logger.debug(f"Updated health for {name}: {mcp.health_status} (failures: {mcp.consecutive_failures})")

    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics"""
        healthy_count = len(self.get_healthy_mcps())

        return {
            'total_mcps': len(self.mcps),
            'healthy_mcps': healthy_count,
            'unhealthy_mcps': len(self.mcps) - healthy_count,
            'categories': len(self.categories),
            'capabilities': len(self.capabilities),
            'transports': len(set(mcp.transport for mcp in self.mcps.values())),
            'has_embeddings': len(self.embeddings) > 0
        }

    def __len__(self):
        """Return number of registered MCPs"""
        return len(self.mcps)

    def __repr__(self):
        return f"MCPRegistry(mcps={len(self.mcps)}, categories={len(self.categories)}, capabilities={len(self.capabilities)})"

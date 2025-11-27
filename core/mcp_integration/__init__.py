"""
Meta-MCP Orchestrator - Integration Package
Allows NubemSFC to orchestrate external MCP servers
"""

from .mcp_registry import MCPRegistry, ExternalMCP
from .mcp_selector import MCPSelector
from .mcp_transports import MCPTransport, StdioTransport, HTTPTransport, SSETransport
from .mcp_connection_pool import MCPConnectionPool
from .hybrid_orchestrator import HybridOrchestrator
from .mcp_credentials_manager import MCPCredentialsManager, get_credentials_manager
from .mcp_initializer import MCPInitializer, initialize_fase1_mcps

__all__ = [
    'MCPRegistry',
    'ExternalMCP',
    'MCPSelector',
    'MCPTransport',
    'StdioTransport',
    'HTTPTransport',
    'SSETransport',
    'MCPConnectionPool',
    'HybridOrchestrator',
    'MCPCredentialsManager',
    'get_credentials_manager',
    'MCPInitializer',
    'initialize_fase1_mcps',
]

__version__ = '1.1.0'

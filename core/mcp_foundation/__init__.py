"""
MCP Foundation Architecture

Core infrastructure for managing 40+ MCPs with:
- Lazy loading
- AI-powered routing
- Circuit breaker pattern
- Health monitoring
- Performance optimization
"""

from .registry import MCPRegistry
from .router import MCPRouter
from .circuit_breaker import MCPCircuitBreaker
from .health_monitor import MCPHealthMonitor
from .lazy_loader import LazyMCPLoader

__all__ = [
    'MCPRegistry',
    'MCPRouter',
    'MCPCircuitBreaker',
    'MCPHealthMonitor',
    'LazyMCPLoader',
]

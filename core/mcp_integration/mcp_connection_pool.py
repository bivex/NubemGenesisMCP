"""
Meta-MCP Orchestrator - Connection Pool Module

Manages a pool of MCP connections with:
- Connection pooling and reuse
- Circuit breaker pattern for fault tolerance
- Health monitoring
- Automatic reconnection
- Resource management
"""

import threading
import time
import logging
from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta
from enum import Enum

from .mcp_registry import MCPRegistry, ExternalMCP
from .mcp_transports import create_transport, MCPTransport

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker implementation for MCP connections.
    Prevents cascading failures by "opening the circuit" after repeated failures.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: Exception = Exception
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            expected_exception: Exception type to catch
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = CircuitState.CLOSED

        self._lock = threading.Lock()

    def call(self, func, *args, **kwargs):
        """
        Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            *args, **kwargs: Function arguments

        Returns:
            Function result

        Raises:
            Exception: If circuit is open or function fails
        """
        with self._lock:
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    logger.info("Circuit breaker moving to HALF_OPEN state")
                else:
                    raise RuntimeError("Circuit breaker is OPEN")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result

        except self.expected_exception as e:
            self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if not self.last_failure_time:
            return False

        time_since_failure = datetime.now() - self.last_failure_time
        return time_since_failure.total_seconds() >= self.recovery_timeout

    def _on_success(self):
        """Handle successful call"""
        with self._lock:
            self.failure_count = 0
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                logger.info("Circuit breaker CLOSED after successful recovery")

    def _on_failure(self):
        """Handle failed call"""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()

            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning(f"Circuit breaker OPENED after {self.failure_count} failures")

    def get_state(self) -> CircuitState:
        """Get current circuit state"""
        return self.state

    def reset(self):
        """Manually reset circuit breaker"""
        with self._lock:
            self.failure_count = 0
            self.last_failure_time = None
            self.state = CircuitState.CLOSED
            logger.info("Circuit breaker manually RESET")


class MCPConnection:
    """
    Represents a single MCP connection with its transport and metadata.
    """

    def __init__(self, mcp: ExternalMCP, transport: MCPTransport):
        """
        Initialize MCP connection.

        Args:
            mcp: ExternalMCP configuration
            transport: MCPTransport instance
        """
        self.mcp = mcp
        self.transport = transport
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=mcp.circuit_breaker_threshold,
            recovery_timeout=60
        )

        self.created_at = datetime.now()
        self.last_used = datetime.now()
        self.use_count = 0
        self.is_connected = False

        self._lock = threading.Lock()

    def connect(self) -> bool:
        """Establish connection"""
        try:
            if self.transport.connect():
                self.is_connected = True
                logger.info(f"✅ Connected to MCP: {self.mcp.name}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Failed to connect to {self.mcp.name}: {e}")
            return False

    def disconnect(self) -> bool:
        """Close connection"""
        try:
            if self.transport.disconnect():
                self.is_connected = False
                logger.info(f"Disconnected from MCP: {self.mcp.name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error disconnecting from {self.mcp.name}: {e}")
            return False

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool with circuit breaker protection.

        Args:
            tool_name: Tool name
            arguments: Tool arguments

        Returns:
            Tool result
        """
        with self._lock:
            self.last_used = datetime.now()
            self.use_count += 1

        def _call():
            return self.transport.call_tool(tool_name, arguments)

        return self.circuit_breaker.call(_call)

    def health_check(self) -> bool:
        """Check connection health"""
        try:
            return self.transport.health_check()
        except Exception as e:
            logger.debug(f"Health check failed for {self.mcp.name}: {e}")
            return False


class MCPConnectionPool:
    """
    Manages a pool of MCP connections with health monitoring and circuit breakers.
    """

    def __init__(self, registry: MCPRegistry):
        """
        Initialize connection pool.

        Args:
            registry: MCPRegistry instance
        """
        self.registry = registry
        self.connections: Dict[str, MCPConnection] = {}

        self._lock = threading.Lock()
        self._health_check_thread: Optional[threading.Thread] = None
        self._should_stop = threading.Event()

        logger.info("MCPConnectionPool initialized")

    def start_health_monitoring(self, interval: int = 60):
        """
        Start background health monitoring.

        Args:
            interval: Check interval in seconds
        """
        if self._health_check_thread and self._health_check_thread.is_alive():
            logger.warning("Health monitoring already running")
            return

        self._should_stop.clear()
        self._health_check_thread = threading.Thread(
            target=self._health_check_loop,
            args=(interval,),
            daemon=True
        )
        self._health_check_thread.start()
        logger.info(f"Health monitoring started (interval: {interval}s)")

    def stop_health_monitoring(self):
        """Stop background health monitoring"""
        if self._health_check_thread:
            self._should_stop.set()
            self._health_check_thread.join(timeout=5)
            logger.info("Health monitoring stopped")

    def _health_check_loop(self, interval: int):
        """Background health check loop"""
        while not self._should_stop.is_set():
            try:
                self._perform_health_checks()
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")

            self._should_stop.wait(interval)

    def _perform_health_checks(self):
        """Perform health checks on all connections"""
        with self._lock:
            connection_names = list(self.connections.keys())

        for name in connection_names:
            connection = self.connections.get(name)
            if not connection:
                continue

            try:
                is_healthy = connection.health_check()
                self.registry.update_health_status(name, is_healthy)

                if not is_healthy:
                    logger.warning(f"Health check failed for {name}, will attempt reconnection")
                    # Try to reconnect
                    connection.disconnect()
                    connection.connect()

            except Exception as e:
                logger.error(f"Health check error for {name}: {e}")
                self.registry.update_health_status(name, False)

    def get_connection(self, mcp_name: str) -> Optional[MCPConnection]:
        """
        Get or create a connection to an MCP.

        Args:
            mcp_name: Name of MCP

        Returns:
            MCPConnection or None if MCP not found
        """
        # Check if connection already exists
        with self._lock:
            if mcp_name in self.connections:
                connection = self.connections[mcp_name]
                if connection.is_connected:
                    return connection

        # Get MCP from registry
        mcp = self.registry.get_mcp(mcp_name)
        if not mcp:
            logger.error(f"MCP '{mcp_name}' not found in registry")
            return None

        # Create new connection
        try:
            transport = create_transport(mcp.transport, mcp.connection, mcp.timeout)
            connection = MCPConnection(mcp, transport)

            if connection.connect():
                with self._lock:
                    self.connections[mcp_name] = connection
                return connection
            else:
                logger.error(f"Failed to connect to {mcp_name}")
                return None

        except Exception as e:
            logger.error(f"Error creating connection to {mcp_name}: {e}")
            return None

    def execute_tool(
        self,
        mcp_name: str,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a tool on an MCP.

        Args:
            mcp_name: MCP name
            tool_name: Tool name
            arguments: Tool arguments

        Returns:
            Tool result or None if failed
        """
        connection = self.get_connection(mcp_name)
        if not connection:
            logger.error(f"Could not get connection to {mcp_name}")
            return None

        try:
            result = connection.execute_tool(tool_name, arguments)
            return result

        except Exception as e:
            logger.error(f"Error executing tool '{tool_name}' on {mcp_name}: {e}")
            # Update health status
            self.registry.update_health_status(mcp_name, False)
            return None

    def close_connection(self, mcp_name: str) -> bool:
        """
        Close a specific connection.

        Args:
            mcp_name: MCP name

        Returns:
            True if closed successfully
        """
        with self._lock:
            connection = self.connections.get(mcp_name)
            if connection:
                connection.disconnect()
                del self.connections[mcp_name]
                logger.info(f"Closed connection to {mcp_name}")
                return True
            return False

    def close_all_connections(self):
        """Close all connections"""
        with self._lock:
            for name, connection in list(self.connections.items()):
                try:
                    connection.disconnect()
                except Exception as e:
                    logger.error(f"Error closing connection to {name}: {e}")

            self.connections.clear()
            logger.info("Closed all connections")

    def get_pool_stats(self) -> Dict[str, Any]:
        """Get pool statistics"""
        with self._lock:
            total_connections = len(self.connections)
            active_connections = sum(1 for c in self.connections.values() if c.is_connected)

            connection_details = []
            for name, conn in self.connections.items():
                connection_details.append({
                    'mcp_name': name,
                    'is_connected': conn.is_connected,
                    'use_count': conn.use_count,
                    'circuit_state': conn.circuit_breaker.get_state().value,
                    'last_used': conn.last_used.isoformat(),
                    'uptime_seconds': (datetime.now() - conn.created_at).total_seconds()
                })

        return {
            'total_connections': total_connections,
            'active_connections': active_connections,
            'inactive_connections': total_connections - active_connections,
            'health_monitoring_active': self._health_check_thread and self._health_check_thread.is_alive(),
            'connections': connection_details
        }

    def __del__(self):
        """Cleanup on destruction"""
        try:
            self.stop_health_monitoring()
            self.close_all_connections()
        except:
            pass

    def __repr__(self):
        return f"MCPConnectionPool(connections={len(self.connections)}, active={sum(1 for c in self.connections.values() if c.is_connected)})"

"""
Meta-MCP Orchestrator - Transport Layer

Handles different transport mechanisms for connecting to external MCPs:
- stdio: For npx, python, local commands
- HTTP: For HTTP-based MCP servers
- SSE: For Server-Sent Events based MCPs
"""

import os
import json
import subprocess
import asyncio
import logging
import requests
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MCPTransport(ABC):
    """
    Abstract base class for MCP transports.
    Defines the interface that all transports must implement.
    """

    def __init__(self, connection_config: Dict[str, Any], timeout: int = 30):
        """
        Initialize transport.

        Args:
            connection_config: Connection configuration from MCP YAML
            timeout: Timeout in seconds for operations
        """
        self.connection_config = connection_config
        self.timeout = timeout
        self.connected = False
        self.last_error: Optional[str] = None

    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to MCP server.

        Returns:
            True if connection successful
        """
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        """
        Close connection to MCP server.

        Returns:
            True if disconnection successful
        """
        pass

    @abstractmethod
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call a tool on the MCP server.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool response
        """
        pass

    @abstractmethod
    def list_tools(self) -> List[Dict[str, Any]]:
        """
        List available tools from MCP server.

        Returns:
            List of tool definitions
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """
        Check if connection is healthy.

        Returns:
            True if healthy
        """
        pass


class StdioTransport(MCPTransport):
    """
    Transport for stdio-based MCPs (npx, python, local commands).
    Communicates via stdin/stdout with JSON-RPC 2.0.
    """

    def __init__(self, connection_config: Dict[str, Any], timeout: int = 30):
        super().__init__(connection_config, timeout)
        self.process: Optional[subprocess.Popen] = None
        self.request_id = 0

    def connect(self) -> bool:
        """Start the stdio process"""
        try:
            command = self.connection_config.get('command')
            args = self.connection_config.get('args', [])
            env = self.connection_config.get('env', {})

            if not command:
                raise ValueError("No command specified in connection config")

            # Build full command
            full_command = [command] + args

            # Prepare environment
            process_env = os.environ.copy()
            process_env.update(env)

            logger.info(f"Starting stdio process: {' '.join(full_command)}")

            # Start process
            self.process = subprocess.Popen(
                full_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=process_env,
                text=True,
                bufsize=1
            )

            # Wait a bit for process to start
            import time
            time.sleep(0.5)

            # Check if process is alive
            if self.process.poll() is not None:
                stderr = self.process.stderr.read()
                raise RuntimeError(f"Process terminated immediately: {stderr}")

            self.connected = True
            logger.info("✅ Stdio transport connected")
            return True

        except Exception as e:
            self.last_error = str(e)
            logger.error(f"❌ Failed to connect stdio transport: {e}")
            self.connected = False
            return False

    def disconnect(self) -> bool:
        """Stop the stdio process"""
        try:
            if self.process:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()

                self.process = None

            self.connected = False
            logger.info("✅ Stdio transport disconnected")
            return True

        except Exception as e:
            self.last_error = str(e)
            logger.error(f"❌ Failed to disconnect stdio transport: {e}")
            return False

    def _send_request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Send JSON-RPC request and get response.

        Args:
            method: JSON-RPC method name
            params: Method parameters

        Returns:
            Response dictionary
        """
        if not self.connected or not self.process:
            raise RuntimeError("Not connected to MCP server")

        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {}
        }

        try:
            # Send request
            request_json = json.dumps(request) + "\n"
            self.process.stdin.write(request_json)
            self.process.stdin.flush()

            # Read response
            response_line = self.process.stdout.readline()

            if not response_line:
                raise RuntimeError("No response from MCP server")

            response = json.loads(response_line)

            # Check for errors
            if "error" in response:
                error = response["error"]
                raise RuntimeError(f"MCP error: {error.get('message', 'Unknown error')}")

            return response

        except Exception as e:
            self.last_error = str(e)
            logger.error(f"❌ Error in stdio request: {e}")
            raise

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool via stdio transport"""
        try:
            response = self._send_request("tools/call", {
                "name": tool_name,
                "arguments": arguments
            })

            return response.get("result", {})

        except Exception as e:
            logger.error(f"❌ Failed to call tool '{tool_name}': {e}")
            raise

    def list_tools(self) -> List[Dict[str, Any]]:
        """List tools via stdio transport"""
        try:
            response = self._send_request("tools/list", {})
            return response.get("result", {}).get("tools", [])

        except Exception as e:
            logger.error(f"❌ Failed to list tools: {e}")
            raise

    def health_check(self) -> bool:
        """Check if stdio process is alive and responsive"""
        try:
            if not self.process or self.process.poll() is not None:
                return False

            # Try to list tools as health check
            self.list_tools()
            return True

        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return False


class HTTPTransport(MCPTransport):
    """
    Transport for HTTP-based MCPs.
    Uses HTTP POST with JSON-RPC 2.0.
    """

    def __init__(self, connection_config: Dict[str, Any], timeout: int = 30):
        super().__init__(connection_config, timeout)
        self.base_url = connection_config.get('url')
        self.headers = connection_config.get('headers', {})
        self.session: Optional[requests.Session] = None
        self.request_id = 0

    def connect(self) -> bool:
        """Initialize HTTP session"""
        try:
            if not self.base_url:
                raise ValueError("No URL specified in connection config")

            self.session = requests.Session()

            # Set default headers
            self.session.headers.update({
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            })

            # Add custom headers
            self.session.headers.update(self.headers)

            # Test connection with health check
            response = self.session.get(
                f"{self.base_url}/health",
                timeout=self.timeout
            )

            if response.status_code == 200:
                self.connected = True
                logger.info(f"✅ HTTP transport connected to {self.base_url}")
                return True
            else:
                raise RuntimeError(f"Health check failed: HTTP {response.status_code}")

        except Exception as e:
            self.last_error = str(e)
            logger.error(f"❌ Failed to connect HTTP transport: {e}")
            self.connected = False
            return False

    def disconnect(self) -> bool:
        """Close HTTP session"""
        try:
            if self.session:
                self.session.close()
                self.session = None

            self.connected = False
            logger.info("✅ HTTP transport disconnected")
            return True

        except Exception as e:
            self.last_error = str(e)
            logger.error(f"❌ Failed to disconnect HTTP transport: {e}")
            return False

    def _send_request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Send HTTP POST with JSON-RPC request.

        Args:
            method: JSON-RPC method name
            params: Method parameters

        Returns:
            Response dictionary
        """
        if not self.connected or not self.session:
            raise RuntimeError("Not connected to MCP server")

        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {}
        }

        try:
            # Determine endpoint
            endpoint = self.connection_config.get('mcp_endpoint', '/mcp')
            url = f"{self.base_url}{endpoint}"

            # Send request
            response = self.session.post(
                url,
                json=request,
                timeout=self.timeout
            )

            response.raise_for_status()

            response_data = response.json()

            # Check for JSON-RPC errors
            if "error" in response_data:
                error = response_data["error"]
                raise RuntimeError(f"MCP error: {error.get('message', 'Unknown error')}")

            return response_data

        except Exception as e:
            self.last_error = str(e)
            logger.error(f"❌ Error in HTTP request: {e}")
            raise

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool via HTTP transport"""
        try:
            response = self._send_request("tools/call", {
                "name": tool_name,
                "arguments": arguments
            })

            return response.get("result", {})

        except Exception as e:
            logger.error(f"❌ Failed to call tool '{tool_name}': {e}")
            raise

    def list_tools(self) -> List[Dict[str, Any]]:
        """List tools via HTTP transport"""
        try:
            response = self._send_request("tools/list", {})
            return response.get("result", {}).get("tools", [])

        except Exception as e:
            logger.error(f"❌ Failed to list tools: {e}")
            raise

    def health_check(self) -> bool:
        """Check HTTP endpoint health"""
        try:
            if not self.session:
                return False

            response = self.session.get(
                f"{self.base_url}/health",
                timeout=self.timeout
            )

            return response.status_code == 200

        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return False


class SSETransport(MCPTransport):
    """
    Transport for Server-Sent Events (SSE) based MCPs.
    Uses SSE for streaming responses from MCP servers.
    """

    def __init__(self, connection_config: Dict[str, Any], timeout: int = 30):
        super().__init__(connection_config, timeout)
        self.base_url = connection_config.get('url')
        self.headers = connection_config.get('headers', {})
        self.session: Optional[requests.Session] = None
        self.request_id = 0

    def connect(self) -> bool:
        """Initialize SSE connection"""
        try:
            if not self.base_url:
                raise ValueError("No URL specified in connection config")

            self.session = requests.Session()

            # Set SSE headers
            self.session.headers.update({
                'Accept': 'text/event-stream',
                'Content-Type': 'application/json'
            })

            # Add custom headers
            self.session.headers.update(self.headers)

            self.connected = True
            logger.info(f"✅ SSE transport connected to {self.base_url}")
            return True

        except Exception as e:
            self.last_error = str(e)
            logger.error(f"❌ Failed to connect SSE transport: {e}")
            self.connected = False
            return False

    def disconnect(self) -> bool:
        """Close SSE connection"""
        try:
            if self.session:
                self.session.close()
                self.session = None

            self.connected = False
            logger.info("✅ SSE transport disconnected")
            return True

        except Exception as e:
            self.last_error = str(e)
            logger.error(f"❌ Failed to disconnect SSE transport: {e}")
            return False

    def _send_sse_request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Send request and read SSE stream.

        Args:
            method: JSON-RPC method name
            params: Method parameters

        Returns:
            Aggregated response dictionary
        """
        if not self.connected or not self.session:
            raise RuntimeError("Not connected to MCP server")

        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {}
        }

        try:
            endpoint = self.connection_config.get('mcp_endpoint', '/mcp')
            url = f"{self.base_url}{endpoint}"

            # Send request with streaming
            response = self.session.post(
                url,
                json=request,
                stream=True,
                timeout=self.timeout
            )

            response.raise_for_status()

            # Read SSE events
            result = None
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')

                    # SSE format: "data: {...}"
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]  # Remove "data: "
                        try:
                            data = json.loads(data_str)

                            # Check for error
                            if "error" in data:
                                error = data["error"]
                                raise RuntimeError(f"MCP error: {error.get('message', 'Unknown error')}")

                            # Aggregate result
                            if "result" in data:
                                result = data

                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON in SSE event: {data_str}")
                            continue

            if result is None:
                raise RuntimeError("No valid result received from SSE stream")

            return result

        except Exception as e:
            self.last_error = str(e)
            logger.error(f"❌ Error in SSE request: {e}")
            raise

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool via SSE transport"""
        try:
            response = self._send_sse_request("tools/call", {
                "name": tool_name,
                "arguments": arguments
            })

            return response.get("result", {})

        except Exception as e:
            logger.error(f"❌ Failed to call tool '{tool_name}': {e}")
            raise

    def list_tools(self) -> List[Dict[str, Any]]:
        """List tools via SSE transport"""
        try:
            response = self._send_sse_request("tools/list", {})
            return response.get("result", {}).get("tools", [])

        except Exception as e:
            logger.error(f"❌ Failed to list tools: {e}")
            raise

    def health_check(self) -> bool:
        """Check SSE connection health"""
        try:
            if not self.session:
                return False

            # Try a simple request
            response = self.session.get(
                f"{self.base_url}/health",
                timeout=self.timeout
            )

            return response.status_code == 200

        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return False


def create_transport(transport_type: str, connection_config: Dict[str, Any], timeout: int = 30) -> MCPTransport:
    """
    Factory function to create the appropriate transport.

    Args:
        transport_type: Type of transport ('stdio', 'http', 'sse')
        connection_config: Connection configuration
        timeout: Timeout in seconds

    Returns:
        MCPTransport instance

    Raises:
        ValueError: If transport_type is not supported
    """
    transports = {
        'stdio': StdioTransport,
        'http': HTTPTransport,
        'sse': SSETransport
    }

    transport_class = transports.get(transport_type.lower())

    if not transport_class:
        raise ValueError(f"Unsupported transport type: {transport_type}. Supported: {list(transports.keys())}")

    return transport_class(connection_config, timeout)

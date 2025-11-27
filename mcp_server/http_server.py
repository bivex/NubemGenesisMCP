#!/usr/bin/env python3
"""
HTTP Wrapper for NubemSuperFClaude MCP Server
Exposes MCP functionality via HTTP endpoints for GKE deployment
"""

import sys
import json
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict
from aiohttp import web
import traceback

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import MCP Server
try:
    from mcp_server.server import NubemSuperFClaudeMCPServer
    logger.info("✅ MCP Server imported successfully")
except Exception as e:
    logger.error(f"❌ Failed to import MCP Server: {e}")
    logger.error(traceback.format_exc())
    sys.exit(1)

# Import Auth Middleware
try:
    from mcp_server.auth_middleware import setup_auth_middleware
    logger.info("✅ Auth middleware imported successfully")
except Exception as e:
    logger.error(f"❌ Failed to import auth middleware: {e}")
    logger.error(traceback.format_exc())
    sys.exit(1)

# Import OAuth Device Flow Handler
try:
    from core.auth import get_device_flow_handler, get_oauth_handler
    from aiohttp import web as aiohttp_web
    import os
    logger.info("✅ OAuth Device Flow handler imported successfully")
except Exception as e:
    logger.error(f"❌ Failed to import OAuth Device Flow handler: {e}")
    logger.error(traceback.format_exc())
    sys.exit(1)


class MCPHttpServer:
    """HTTP wrapper for MCP Server"""

    def __init__(self, host='0.0.0.0', port=8080):
        self.host = host
        self.port = port
        self.mcp_server = None
        self.app = web.Application()

        # Setup authentication middleware
        setup_auth_middleware(self.app)

        self._setup_routes()

    def _setup_routes(self):
        """Setup HTTP routes"""
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_get('/status', self.get_status)
        self.app.router.add_post('/mcp', self.handle_mcp_request)
        self.app.router.add_post('/tools/call', self.handle_tool_call)
        self.app.router.add_get('/tools/list', self.list_tools)
        self.app.router.add_get('/personas/list', self.list_personas)

        # OAuth Device Flow routes
        self.app.router.add_post('/auth/device/code', self.device_code_request)
        self.app.router.add_post('/auth/device/token', self.device_token_poll)
        self.app.router.add_post('/auth/device/verify', self.device_verify)
        self.app.router.add_get('/device', self.device_authorization_page)
        # Note: OAuth callback is handled by /auth/google/callback in secrets_ui_routes.py

        # Serve static files for device flow UI
        self.app.router.add_static('/static', path=str(Path(__file__).parent.parent / 'static'))

    async def initialize(self):
        """Initialize MCP server"""
        try:
            logger.info("Initializing MCP Server...")
            self.mcp_server = NubemSuperFClaudeMCPServer()
            logger.info("✅ MCP Server initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize MCP Server: {e}")
            logger.error(traceback.format_exc())
            raise

    async def health_check(self, request):
        """Health check endpoint"""
        return web.json_response({
            "status": "healthy",
            "service": "NubemSuperFClaude MCP Server",
            "version": "1.2.0-auth",
            "features": {
                "authentication": True,
                "authorization": True,
                "rate_limiting": True,
                "audit_logging": True
            }
        })

    async def get_status(self, request):
        """Get system status"""
        try:
            if not self.mcp_server:
                return web.json_response({
                    "error": "MCP Server not initialized"
                }, status=503)

            # Call get_system_status tool
            mcp_request = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "get_system_status",
                    "arguments": {}
                },
                "id": 1
            }

            result = await self.mcp_server.handle_request(mcp_request)
            return web.json_response(result)

        except Exception as e:
            logger.error(f"Error in get_status: {e}")
            logger.error(traceback.format_exc())
            return web.json_response({
                "error": str(e)
            }, status=500)

    async def handle_mcp_request(self, request):
        """Handle MCP JSON-RPC request"""
        try:
            if not self.mcp_server:
                return web.json_response({
                    "error": "MCP Server not initialized"
                }, status=503)

            body = await request.json()
            result = await self.mcp_server.handle_request(body)
            return web.json_response(result)

        except Exception as e:
            logger.error(f"Error handling MCP request: {e}")
            logger.error(traceback.format_exc())
            return web.json_response({
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": str(e)
                },
                "id": None
            }, status=500)

    async def handle_tool_call(self, request):
        """Handle tool call (simplified endpoint)"""
        try:
            if not self.mcp_server:
                return web.json_response({
                    "error": "MCP Server not initialized"
                }, status=503)

            body = await request.json()

            # Wrap in MCP request format
            mcp_request = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": body,
                "id": 1
            }

            result = await self.mcp_server.handle_request(mcp_request)
            return web.json_response(result)

        except Exception as e:
            logger.error(f"Error in tool call: {e}")
            logger.error(traceback.format_exc())
            return web.json_response({
                "error": str(e)
            }, status=500)

    async def list_tools(self, request):
        """List available tools"""
        try:
            if not self.mcp_server:
                return web.json_response({
                    "error": "MCP Server not initialized"
                }, status=503)

            mcp_request = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": {},
                "id": 1
            }

            result = await self.mcp_server.handle_request(mcp_request)
            return web.json_response(result)

        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            logger.error(traceback.format_exc())
            return web.json_response({
                "error": str(e)
            }, status=500)

    async def list_personas(self, request):
        """List available personas"""
        try:
            if not self.mcp_server:
                return web.json_response({
                    "error": "MCP Server not initialized"
                }, status=503)

            mcp_request = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "list_personas",
                    "arguments": {}
                },
                "id": 1
            }

            result = await self.mcp_server.handle_request(mcp_request)
            return web.json_response(result)

        except Exception as e:
            logger.error(f"Error listing personas: {e}")
            logger.error(traceback.format_exc())
            return web.json_response({
                "error": str(e)
            }, status=500)

    # ========================================================================
    # OAuth Device Flow Handlers
    # ========================================================================

    async def device_code_request(self, request):
        """Handle device code request (POST /auth/device/code)"""
        try:
            device_flow = get_device_flow_handler()
            if not device_flow:
                return web.json_response({
                    "error": "device_flow_disabled",
                    "error_description": "OAuth Device Flow is not enabled"
                }, status=503)

            body = await request.json()
            client_info = body.get("client_info", {})

            # Extract parameters for device code generation
            client_id = client_info.get("client_name", "unknown-client")
            scope = "read write"  # Default scope for CLI clients
            client_ip = request.remote or "unknown"
            user_agent = request.headers.get('User-Agent', 'unknown')

            result = await device_flow.generate_device_code(
                client_id=client_id,
                scope=scope,
                client_ip=client_ip,
                user_agent=user_agent
            )
            logger.info(f"Device code generated: user_code={result['user_code']}")

            return web.json_response(result, status=200)

        except Exception as e:
            logger.error(f"Error generating device code: {e}")
            logger.error(traceback.format_exc())
            return web.json_response({
                "error": "server_error",
                "error_description": "Internal server error"
            }, status=500)

    async def device_token_poll(self, request):
        """Handle device token polling (POST /auth/device/token)"""
        try:
            device_flow = get_device_flow_handler()
            if not device_flow:
                return web.json_response({
                    "error": "device_flow_disabled",
                    "error_description": "OAuth Device Flow is not enabled"
                }, status=503)

            body = await request.json()
            device_code = body.get("device_code")
            client_id = body.get("client_id", "unknown-client")  # Extract client_id from request

            if not device_code:
                return web.json_response({
                    "error": "invalid_request",
                    "error_description": "Missing device_code parameter"
                }, status=400)

            result = await device_flow.poll_for_token(device_code, client_id)

            # Check for error responses (authorization_pending, slow_down, etc.)
            if "error" in result:
                status_code = 400 if result["error"] in ["expired_token", "access_denied"] else 200
                return web.json_response(result, status=status_code)

            # Success - return token
            logger.info(f"Device token issued: device={device_code[:15]}...")
            return web.json_response(result, status=200)

        except Exception as e:
            logger.error(f"Error polling device token: {e}")
            logger.error(traceback.format_exc())
            return web.json_response({
                "error": "server_error",
                "error_description": "Internal server error"
            }, status=500)

    async def device_verify(self, request):
        """Handle device verification (POST /auth/device/verify)"""
        try:
            device_flow = get_device_flow_handler()
            if not device_flow:
                return web.json_response({
                    "error": "device_flow_disabled",
                    "error_description": "OAuth Device Flow is not enabled"
                }, status=503)

            body = await request.json()
            user_code = body.get("user_code", "").upper().strip()

            if not user_code:
                return web.json_response({
                    "error": "invalid_request",
                    "error_description": "Missing user_code parameter"
                }, status=400)

            # Verify user code exists
            device_code = await device_flow.verify_user_code(user_code)

            if device_code is None:
                logger.warning(f"Invalid user code: {user_code}")
                return web.json_response({
                    "error": "invalid_code",
                    "error_description": "Invalid or expired user code"
                }, status=400)

            # Get OAuth handler
            oauth_handler = get_oauth_handler()

            if not oauth_handler.is_configured():
                logger.error("OAuth not configured")
                return web.json_response({
                    "error": "server_error",
                    "error_description": "OAuth not configured"
                }, status=500)

            # Generate OAuth URL
            oauth_data = oauth_handler.get_authorization_url()

            # Store OAuth state -> device_code mapping
            await device_flow.storage.store_oauth_state(
                state=oauth_data["state"],
                device_code=device_code,
                ttl=900  # 15 minutes
            )

            logger.info(f"Device verification successful: user_code={user_code}")

            return web.json_response({
                "authorization_url": oauth_data["authorization_url"]
            }, status=200)

        except Exception as e:
            logger.error(f"Error verifying user code: {e}")
            logger.error(traceback.format_exc())
            return web.json_response({
                "error": "server_error",
                "error_description": "Internal server error"
            }, status=500)

    async def device_authorization_page(self, request):
        """Serve device authorization HTML page (GET /device)"""
        try:
            # Get user_code from query string (optional)
            user_code = request.query.get('user_code', '')

            # Read HTML template
            template_path = Path(__file__).parent.parent / 'templates' / 'device_authorization.html'

            if not template_path.exists():
                return web.json_response({
                    "error": "template_not_found",
                    "error_description": "Device authorization page not found"
                }, status=500)

            with open(template_path, 'r') as f:
                html_content = f.read()

            # Replace template variable
            html_content = html_content.replace('{{ user_code }}', user_code)

            return aiohttp_web.Response(text=html_content, content_type='text/html')

        except Exception as e:
            logger.error(f"Error serving device authorization page: {e}")
            logger.error(traceback.format_exc())
            return web.json_response({
                "error": "server_error",
                "error_description": "Internal server error"
            }, status=500)

    async def start(self):
        """Start HTTP server"""
        await self.initialize()

        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()

        logger.info(f"🚀 MCP HTTP Server running on http://{self.host}:{self.port}")
        logger.info(f"🔒 Authentication: ENABLED (Hybrid: API Key + OAuth)")
        logger.info(f"   Health: http://{self.host}:{self.port}/health")
        logger.info(f"   Status: http://{self.host}:{self.port}/status")
        logger.info(f"   Tools: http://{self.host}:{self.port}/tools/list")
        logger.info(f"   Personas: http://{self.host}:{self.port}/personas/list")
        logger.info(f"🔐 OAuth Device Flow: ENABLED")
        logger.info(f"   Device Code: http://{self.host}:{self.port}/auth/device/code")
        logger.info(f"   Device Auth: http://{self.host}:{self.port}/device")

        # Keep running
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("Shutting down...")


async def main():
    """Main entry point"""
    server = MCPHttpServer(host='0.0.0.0', port=8080)
    await server.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)

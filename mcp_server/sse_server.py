#!/usr/bin/env python3
"""
MCP Server with SSE (Server-Sent Events) Transport
Implements MCP Streamable HTTP specification (2025-03-26)
"""

import sys
import json
import asyncio
import logging
import traceback
from pathlib import Path
from typing import Any, Dict, Optional
from aiohttp import web
import aiohttp

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import components
try:
    from mcp_server.server import NubemSuperFClaudeMCPServer
    from mcp_server.sse_handler import sse_handler, init_sse_handler, shutdown_sse_handler
    from mcp_server.session_manager import (
        init_session_manager,
        shutdown_session_manager,
        get_session_manager
    )
    logger.info("✅ All MCP components imported successfully")
except Exception as e:
    logger.error(f"❌ Failed to import components: {e}")
    logger.error(traceback.format_exc())
    sys.exit(1)


class MCPSSEServer:
    """
    MCP Server with SSE transport
    Implements Streamable HTTP as per MCP spec 2025-03-26
    """

    def __init__(self, host='0.0.0.0', port=8080):
        self.host = host
        self.port = port
        self.mcp_server = None
        self.app = web.Application()
        self.allowed_origins = [
            'http://localhost:*',
            'http://127.0.0.1:*',
            '*'  # Allow all for now (configure in production)
        ]
        self._setup_routes()
        self._setup_middlewares()

    def _setup_routes(self):
        """Setup HTTP routes"""
        # MCP Streamable HTTP endpoint (spec 2025-03-26)
        self.app.router.add_post('/mcp', self.handle_mcp_post)
        self.app.router.add_get('/mcp', self.handle_mcp_get)

        # Health and status endpoints
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_get('/status', self.get_status)

        # Convenience endpoints (backwards compatible)
        self.app.router.add_get('/tools/list', self.list_tools)
        self.app.router.add_get('/personas/list', self.list_personas)
        self.app.router.add_post('/tools/call', self.handle_tool_call)

        # Setup Secrets UI routes
        try:
            from mcp_server.secrets_ui_routes import setup_secrets_ui
            setup_secrets_ui(self.app)
            logger.info("✅ Secrets UI routes integrated")
        except Exception as e:
            logger.warning(f"⚠️ Secrets UI not available: {e}")
            # Continue without Secrets UI (non-critical)

    def _setup_middlewares(self):
        """Setup middleware"""
        self.app.middlewares.append(self._cors_middleware)

    @web.middleware
    async def _cors_middleware(self, request, handler):
        """CORS middleware"""
        # Handle preflight
        if request.method == 'OPTIONS':
            response = web.Response()
        else:
            response = await handler(request)

        # Add CORS headers
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Accept, Mcp-Session-Id, Last-Event-ID'
        response.headers['Access-Control-Expose-Headers'] = 'Mcp-Session-Id'

        return response

    async def initialize(self):
        """Initialize MCP server and components"""
        try:
            logger.info("Initializing MCP Server components...")

            # Initialize session manager
            await init_session_manager(redis_client=None, timeout=1800)

            # Initialize SSE handler
            await init_sse_handler()

            # Initialize MCP server
            self.mcp_server = NubemSuperFClaudeMCPServer()

            logger.info("✅ All components initialized successfully")

        except Exception as e:
            logger.error(f"❌ Failed to initialize: {e}")
            logger.error(traceback.format_exc())
            raise

    async def health_check(self, request):
        """Health check endpoint"""
        session_mgr = get_session_manager()
        stats = await session_mgr.get_session_stats() if session_mgr else {}

        return web.json_response({
            "status": "healthy",
            "service": "NubemSuperFClaude MCP Server",
            "version": "2.0.0-sse",
            "transport": "streamable-http",
            "spec": "2025-03-26",
            "sessions": stats
        })

    async def get_status(self, request):
        """Get system status"""
        try:
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
            return web.json_response({"error": str(e)}, status=500)

    async def handle_mcp_post(self, request):
        """
        Handle POST /mcp - Client sends JSON-RPC request
        As per MCP spec 2025-03-26
        """
        try:
            # Validate Origin
            origin = request.headers.get('Origin')
            if not sse_handler.validate_origin(origin, self.allowed_origins):
                return web.json_response({
                    "error": "Invalid origin"
                }, status=403)

            # Get or create session
            session_mgr = get_session_manager()
            session_id = request.headers.get('Mcp-Session-Id')

            if session_id:
                session = await session_mgr.get_session(session_id)
                if not session:
                    # Session expired, create new one
                    session = await session_mgr.create_session()
            else:
                # Create new session
                session = await session_mgr.create_session()

            # Parse JSON-RPC request
            try:
                body = await request.json()
            except json.JSONDecodeError:
                return web.json_response({
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32700,
                        "message": "Parse error"
                    },
                    "id": None
                }, status=400)

            # Check Accept header
            accept = request.headers.get('Accept', '')
            wants_sse = 'text/event-stream' in accept

            # Get or create SSE stream for this session
            stream = sse_handler.get_stream(session.session_id)
            if not stream:
                stream = sse_handler.create_stream(session.session_id)

            # Process request
            response = await self.mcp_server.handle_request(body)

            # Return based on Accept header
            if wants_sse:
                # Return SSE stream
                return await self._stream_sse_response(request, session, stream, response)
            else:
                # Return JSON response
                resp = web.json_response(response)
                resp.headers['Mcp-Session-Id'] = session.session_id
                return resp

        except Exception as e:
            logger.error(f"Error in handle_mcp_post: {e}")
            logger.error(traceback.format_exc())
            return web.json_response({
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                },
                "id": None
            }, status=500)

    async def handle_mcp_get(self, request):
        """
        Handle GET /mcp - Open SSE stream
        As per MCP spec 2025-03-26
        """
        try:
            # Validate Origin
            origin = request.headers.get('Origin')
            if not sse_handler.validate_origin(origin, self.allowed_origins):
                return web.json_response({
                    "error": "Invalid origin"
                }, status=403)

            # Check Accept header
            accept = request.headers.get('Accept', '')
            if 'text/event-stream' not in accept:
                return web.json_response({
                    "error": "Accept: text/event-stream required"
                }, status=400)

            # Get or create session
            session_mgr = get_session_manager()
            session_id = request.headers.get('Mcp-Session-Id')

            if session_id:
                session = await session_mgr.get_session(session_id)
                if not session:
                    session = await session_mgr.create_session()
            else:
                session = await session_mgr.create_session()

            # Get or create stream
            stream = sse_handler.get_stream(session.session_id)
            if not stream:
                stream = sse_handler.create_stream(session.session_id)

            # Check for resumability
            last_event_id = request.headers.get('Last-Event-ID')

            # Create SSE response
            response = web.StreamResponse(
                status=200,
                reason='OK',
                headers={
                    'Content-Type': 'text/event-stream',
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'Mcp-Session-Id': session.session_id,
                    'X-Accel-Buffering': 'no'  # Disable nginx buffering
                }
            )

            await response.prepare(request)

            # Resume from last event if requested
            if last_event_id:
                async for event_data in sse_handler.resume_stream(stream, last_event_id):
                    await response.write(event_data.encode('utf-8'))

            # Keep connection alive with heartbeats
            try:
                while True:
                    # Send heartbeat every 30 seconds
                    heartbeat = sse_handler.create_heartbeat_event(stream)
                    await response.write(heartbeat.format().encode('utf-8'))
                    await asyncio.sleep(30)

            except (ConnectionResetError, asyncio.CancelledError):
                logger.info(f"SSE connection closed for session {session.session_id}")

            return response

        except Exception as e:
            logger.error(f"Error in handle_mcp_get: {e}")
            logger.error(traceback.format_exc())
            return web.json_response({
                "error": str(e)
            }, status=500)

    async def _stream_sse_response(self, request, session, stream, response_data):
        """Stream a JSON-RPC response as SSE"""
        sse_response = web.StreamResponse(
            status=200,
            reason='OK',
            headers={
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Mcp-Session-Id': session.session_id,
                'X-Accel-Buffering': 'no'
            }
        )

        await sse_response.prepare(request)

        # Send response as SSE event
        async for event_data in sse_handler.stream_json_rpc_response(stream, response_data):
            await sse_response.write(event_data.encode('utf-8'))

        # Close stream after sending response
        await sse_response.write_eof()

        return sse_response

    async def list_tools(self, request):
        """List available tools (convenience endpoint)"""
        try:
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
            return web.json_response({"error": str(e)}, status=500)

    async def list_personas(self, request):
        """List available personas (convenience endpoint)"""
        try:
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
            return web.json_response({"error": str(e)}, status=500)

    async def handle_tool_call(self, request):
        """Handle tool call (convenience endpoint)"""
        try:
            body = await request.json()

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
            return web.json_response({"error": str(e)}, status=500)

    async def start(self):
        """Start SSE server"""
        await self.initialize()

        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()

        logger.info(f"🚀 MCP SSE Server running on http://{self.host}:{self.port}")
        logger.info(f"   Protocol: MCP Streamable HTTP (Spec 2025-03-26)")
        logger.info(f"   SSE Endpoint: POST/GET http://{self.host}:{self.port}/mcp")
        logger.info(f"   Health: http://{self.host}:{self.port}/health")
        logger.info(f"   Status: http://{self.host}:{self.port}/status")
        logger.info(f"   Tools: http://{self.host}:{self.port}/tools/list")
        logger.info(f"   Personas: http://{self.host}:{self.port}/personas/list")
        logger.info(f"🔐 Secrets UI: http://{self.host}:{self.port}/secrets")
        logger.info(f"   API: http://{self.host}:{self.port}/api/v1/secrets")

        # Keep running
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            await self.shutdown()

    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down MCP SSE Server...")
        await shutdown_sse_handler()
        await shutdown_session_manager()
        logger.info("Shutdown complete")


async def main():
    """Main entry point"""
    server = MCPSSEServer(host='0.0.0.0', port=8080)
    await server.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)

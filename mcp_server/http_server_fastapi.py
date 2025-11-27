#!/usr/bin/env python3
"""
FastAPI HTTP Server for NubemSuperFClaude MCP Server

Multi-tenant architecture with authentication, rate limiting, and RLS.
Design approved by expert panel (see AUTH_MIDDLEWARE_EXPERT_DEBATE.md).

Migration: Converted from aiohttp to FastAPI to align with expert consensus.
"""

import sys
import json
import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, Response, status, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import core components
try:
    from mcp_server.server import NubemSuperFClaudeMCPServer
    logger.info("✅ MCP Server imported successfully")
except Exception as e:
    logger.error(f"❌ Failed to import MCP Server: {e}")
    import traceback
    logger.error(traceback.format_exc())
    sys.exit(1)

# Import middleware
try:
    from mcp_server.middleware import (
        AuthenticationMiddleware,
        RLSMiddleware,
        public_endpoint
    )
    from core.cache import TwoTierCache
    from core.database.connection import (
        init_database_engine,
        close_database_engine,
        check_database_connection
    )
    logger.info("✅ Middleware and database components imported successfully")
except Exception as e:
    logger.error(f"❌ Failed to import middleware: {e}")
    import traceback
    logger.error(traceback.format_exc())
    sys.exit(1)

# Import API routers
try:
    from mcp_server.api.tenants import router as tenants_router
    from mcp_server.api.api_keys import router as api_keys_router
    from mcp_server.api.usage import router as usage_router
    logger.info("✅ API routers imported successfully")
except Exception as e:
    logger.error(f"❌ Failed to import API routers: {e}")
    import traceback
    logger.error(traceback.format_exc())
    sys.exit(1)

# Import OAuth routes
try:
    from mcp_server import auth_routes
    logger.info("✅ OAuth routes imported successfully")
except Exception as e:
    logger.error(f"❌ Failed to import OAuth routes: {e}")
    import traceback
    logger.error(traceback.format_exc())
    sys.exit(1)


# Initialize FastAPI app
app = FastAPI(
    title="NubemSuperFClaude MCP Server",
    version="1.3.0-multitenant",
    description="Multi-tenant MCP server with authentication and RLS",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Global MCP server instance
mcp_server: Optional[NubemSuperFClaudeMCPServer] = None

# Global cache instance
cache: Optional[TwoTierCache] = None

# Global templates instance
templates: Optional[Jinja2Templates] = None

# Mount static files (for CSS, JS, images)
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.info(f"✅ Static files mounted: {static_dir}")
else:
    logger.warning(f"⚠️ Static directory not found: {static_dir}")


@app.on_event("startup")
async def startup_event():
    """
    Initialize components on startup

    Order:
    1. Initialize database engine
    2. Initialize Redis cache
    3. Initialize MCP server
    4. Add middleware (in correct order)
    """
    global mcp_server, cache, templates

    logger.info("🚀 Starting NubemSuperFClaude MCP Server...")

    try:
        # 1. Initialize database engine
        logger.info("1️⃣ Initializing database engine...")
        init_database_engine(
            pool_size=20,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=3600,
            echo=False
        )

        # Test database connection
        try:
            if await check_database_connection():
                logger.info("   ✅ Database connection successful")
        except Exception as e:
            logger.warning(f"   ⚠️ Database connection check failed: {e}")
            logger.warning("   ⚠️ Continuing anyway (migrations may not be applied)")

        # 2. Initialize Redis cache
        logger.info("2️⃣ Initializing two-tier cache...")
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        cache = TwoTierCache(
            redis_url=redis_url,
            l1_max_size=1000,
            l1_ttl_seconds=300,  # 5 minutes
            l2_ttl_seconds=900,  # 15 minutes
            redis_timeout=1,
            circuit_breaker_failures=3,
            circuit_breaker_timeout=30
        )
        logger.info(f"   ✅ Cache initialized: {redis_url}")

        # 3. Initialize MCP server
        logger.info("3️⃣ Initializing MCP server...")
        mcp_server = NubemSuperFClaudeMCPServer()
        logger.info("   ✅ MCP server initialized")

        # 4. Add middleware (in correct order - see expert panel decision)
        logger.info("4️⃣ Adding middleware stack...")

        # Middleware order (CRITICAL - approved by panel):
        # 1. CORS (if needed)
        # 2. Authentication
        # 3. RLS
        # 4. [Routes]

        # Add authentication middleware
        app.add_middleware(AuthenticationMiddleware, cache=cache)
        logger.info("   ✅ Authentication middleware added")

        # Add RLS middleware
        app.add_middleware(RLSMiddleware)
        logger.info("   ✅ RLS middleware added")

        # Add CORS (optional)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Configure based on your needs
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        logger.info("   ✅ CORS middleware added")

        # 5. Initialize templates
        logger.info("5️⃣ Initializing templates...")
        templates_dir = Path(__file__).parent.parent / "templates"
        if templates_dir.exists():
            templates = Jinja2Templates(directory=str(templates_dir))
            logger.info(f"   ✅ Templates initialized: {templates_dir}")
        else:
            logger.warning(f"   ⚠️ Templates directory not found: {templates_dir}")
            templates = None

        # 6. Initialize OAuth routes with dependencies
        if templates:
            logger.info("6️⃣ Initializing OAuth routes...")
            auth_routes.init_auth_routes(cache, templates)
            app.include_router(auth_routes.router)
            logger.info("   ✅ OAuth routes registered")
        else:
            logger.warning("   ⚠️ Skipping OAuth routes (templates not found)")

        # 7. Register Tenant API routers
        logger.info("7️⃣ Registering API routers...")
        app.include_router(tenants_router)
        app.include_router(api_keys_router)
        app.include_router(usage_router)
        logger.info("   ✅ Tenant Management API registered")
        logger.info("   ✅ API Key Management API registered")
        logger.info("   ✅ Usage & Quota API registered")

        logger.info("✅ Startup complete!")
        logger.info(f"   Version: 1.4.0-oauth-tenant")
        logger.info(f"   Features: OAuth, Tenant Auto-Provisioning, Authentication, RLS, Tenant API")

    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """
    Cleanup on shutdown
    """
    logger.info("🛑 Shutting down...")

    try:
        # Close database connections
        await close_database_engine()
        logger.info("✅ Database connections closed")

    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


# ============================================================================
# PUBLIC ENDPOINTS (no authentication required)
# ============================================================================

@app.get("/health")
@public_endpoint
async def health_check():
    """
    Health check endpoint

    Public endpoint - no authentication required
    """
    return {
        "status": "healthy",
        "service": "NubemSuperFClaude MCP Server",
        "version": "1.3.0-multitenant",
        "features": {
            "authentication": True,
            "rls": True,
            "two_tier_cache": True,
            "multi_tenant": True
        }
    }


@app.get("/metrics")
@public_endpoint
async def metrics():
    """
    Prometheus metrics endpoint

    Public endpoint - no authentication required
    """
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

    metrics_output = generate_latest()
    return Response(content=metrics_output, media_type=CONTENT_TYPE_LATEST)


# ============================================================================
# AUTHENTICATED ENDPOINTS (require X-API-Key header)
# ============================================================================

@app.get("/status")
async def get_status(request: Request):
    """
    Get system status

    Requires authentication (X-API-Key header)
    """
    try:
        if not mcp_server:
            return JSONResponse(
                status_code=503,
                content={"error": "MCP Server not initialized"}
            )

        # Get tenant context from request.state (set by AuthenticationMiddleware)
        tenant_id = request.state.tenant_id
        tenant_plan = request.state.tenant_plan

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

        result = await mcp_server.handle_request(mcp_request)

        # Add tenant context to response
        if "result" in result:
            result["tenant_context"] = {
                "tenant_id": tenant_id,
                "plan": tenant_plan
            }

        return result

    except Exception as e:
        logger.error(f"Error in get_status: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "request_id": request.state.request_id
            }
        )


@app.post("/mcp")
async def handle_mcp_request(request: Request):
    """
    Handle MCP JSON-RPC request

    Requires authentication (X-API-Key header)

    Request body:
    {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {...},
        "id": 1
    }
    """
    try:
        if not mcp_server:
            return JSONResponse(
                status_code=503,
                content={"error": "MCP Server not initialized"}
            )

        body = await request.json()

        # Inject tenant context into request
        body["_tenant_context"] = {
            "tenant_id": request.state.tenant_id,
            "tenant_plan": request.state.tenant_plan,
            "api_key_id": request.state.api_key_id,
            "api_key_role": request.state.api_key_role
        }

        result = await mcp_server.handle_request(body)
        return result

    except Exception as e:
        logger.error(f"Error handling MCP request: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": "Internal server error"
                },
                "id": None,
                "request_id": request.state.request_id
            }
        )


@app.post("/tools/call")
async def handle_tool_call(request: Request):
    """
    Handle tool call (simplified endpoint)

    Requires authentication (X-API-Key header)

    Request body:
    {
        "name": "tool_name",
        "arguments": {...}
    }
    """
    try:
        if not mcp_server:
            return JSONResponse(
                status_code=503,
                content={"error": "MCP Server not initialized"}
            )

        body = await request.json()

        # Wrap in MCP request format
        mcp_request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": body,
            "id": 1,
            "_tenant_context": {
                "tenant_id": request.state.tenant_id,
                "tenant_plan": request.state.tenant_plan,
                "api_key_id": request.state.api_key_id,
                "api_key_role": request.state.api_key_role
            }
        }

        result = await mcp_server.handle_request(mcp_request)
        return result

    except Exception as e:
        logger.error(f"Error in tool call: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "request_id": request.state.request_id
            }
        )


@app.get("/tools/list")
async def list_tools(request: Request):
    """
    List available tools

    Requires authentication (X-API-Key header)
    """
    try:
        if not mcp_server:
            return JSONResponse(
                status_code=503,
                content={"error": "MCP Server not initialized"}
            )

        mcp_request = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": 1,
            "_tenant_context": {
                "tenant_id": request.state.tenant_id,
                "tenant_plan": request.state.tenant_plan
            }
        }

        result = await mcp_server.handle_request(mcp_request)
        return result

    except Exception as e:
        logger.error(f"Error listing tools: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "request_id": request.state.request_id
            }
        )


@app.get("/personas/list")
async def list_personas(request: Request):
    """
    List available personas

    Requires authentication (X-API-Key header)
    """
    try:
        if not mcp_server:
            return JSONResponse(
                status_code=503,
                content={"error": "MCP Server not initialized"}
            )

        mcp_request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "list_personas",
                "arguments": {}
            },
            "id": 1,
            "_tenant_context": {
                "tenant_id": request.state.tenant_id,
                "tenant_plan": request.state.tenant_plan
            }
        }

        result = await mcp_server.handle_request(mcp_request)
        return result

    except Exception as e:
        logger.error(f"Error listing personas: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "request_id": request.state.request_id
            }
        )


@app.get("/cache/stats")
async def get_cache_stats(request: Request):
    """
    Get cache statistics

    Requires authentication (X-API-Key header)
    Admin role only
    """
    try:
        # Check if user has admin role
        if request.state.api_key_role != "admin":
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Forbidden",
                    "message": "Admin role required"
                }
            )

        if not cache:
            return JSONResponse(
                status_code=503,
                content={"error": "Cache not initialized"}
            )

        stats = cache.get_stats()
        health = cache.health_check()

        return {
            "stats": stats,
            "health": health
        }

    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "request_id": request.state.request_id
            }
        )


# ============================================================================
# MAIN
# ============================================================================

def main():
    """
    Main entry point
    """
    # Get configuration from environment
    host = os.getenv("HTTP_HOST", "0.0.0.0")
    port = int(os.getenv("HTTP_PORT", "8080"))
    workers = int(os.getenv("HTTP_WORKERS", "1"))
    log_level = os.getenv("LOG_LEVEL", "info").lower()

    logger.info(f"🚀 Starting server on {host}:{port}")
    logger.info(f"   Workers: {workers}")
    logger.info(f"   Log level: {log_level}")

    # Run with uvicorn
    uvicorn.run(
        "mcp_server.http_server_fastapi:app",
        host=host,
        port=port,
        workers=workers,
        log_level=log_level,
        reload=False,  # Disable reload in production
        access_log=True
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)

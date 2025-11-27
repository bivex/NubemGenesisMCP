#!/usr/bin/env python3
"""
NubemSuperFClaude - Main API Entry Point
Integrates secrets API and OAuth authentication
"""

import os
import sys
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

# Import routers
from core.api.secrets_api import app as secrets_app
from core.api.auth import router as auth_router

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Setup paths
BASE_DIR = Path(__file__).parent.parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# Initialize Jinja2 templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Get session secret
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-this-in-production-very-long-secret-key-min-32-chars")

# Create main app (reuse secrets_app which already has CORS, rate limiting, etc.)
app = secrets_app

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Add session middleware for OAuth
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="nubemsuperfclaude_session",
    max_age=86400,  # 24 hours
    https_only=os.getenv("NODE_ENV") == "production"
)

# Include auth router
app.include_router(auth_router)

# HTML Routes
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Root endpoint - redirect to login or dashboard"""
    # Check if user is authenticated via session
    if "user" in request.session:
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "user": request.session.get("user")
        })
    return templates.TemplateResponse("login.html", {
        "request": request,
        "dev_mode": os.getenv("NODE_ENV") != "production"
    })


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    return templates.TemplateResponse("login.html", {
        "request": request,
        "dev_mode": os.getenv("NODE_ENV") != "production"
    })


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Dashboard page"""
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": request.session.get("user")
    })


# API info endpoint
@app.get("/api/info")
async def api_info():
    """API information endpoint"""
    return {
        "name": "NubemSuperFClaude Secrets API",
        "version": "1.0.0",
        "docs": "/api/docs",
        "health": "/health",
        "auth": {
            "login": "/auth/login",
            "logout": "/auth/logout",
            "me": "/api/v1/me"
        },
        "endpoints": {
            "list_secrets": "/api/v1/secrets",
            "get_secret": "/api/v1/secrets/{name}",
            "create_secret": "/api/v1/secrets",
            "update_secret": "/api/v1/secrets/{name}",
            "delete_secret": "/api/v1/secrets/{name}"
        }
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8888))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info(f"🚀 Starting NubemSuperFClaude Secrets API on {host}:{port}")

    uvicorn.run(
        "core.api.main:app",
        host=host,
        port=port,
        reload=os.getenv("NODE_ENV") != "production",
        log_level="info"
    )

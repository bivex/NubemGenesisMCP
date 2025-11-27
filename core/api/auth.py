#!/usr/bin/env python3
"""
NubemSuperFClaude - OAuth 2.0 Authentication
Google OAuth 2.0 integration for FastAPI
"""

import os
import logging
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware

# Import from secrets_api
from core.api.secrets_api import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, ALLOWED_DOMAIN, Token

# Configure logging
logger = logging.getLogger(__name__)

# OAuth configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8080/auth/callback")

# Validate OAuth configuration
if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    logger.warning("⚠️  Google OAuth credentials not configured. OAuth endpoints will not work.")
    logger.warning("   Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables.")

# Initialize OAuth
oauth = OAuth()

if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    oauth.register(
        name='google',
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile',
            'prompt': 'select_account'  # Always show account selection
        }
    )

# Create router
router = APIRouter(prefix="/auth", tags=["authentication"])


@router.get("/login")
async def login(request: Request):
    """
    Initiate Google OAuth 2.0 login flow
    """
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth not configured. Please contact administrator."
        )

    # Store the redirect URI in session for callback
    redirect_uri = request.url_for('auth_callback')

    logger.info(f"Initiating OAuth login with redirect URI: {redirect_uri}")

    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def auth_callback(request: Request):
    """
    OAuth 2.0 callback endpoint
    Handles the redirect from Google after user authentication
    """
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth not configured"
        )

    try:
        # Get access token from Google
        token = await oauth.google.authorize_access_token(request)

        # Get user info
        user_info = token.get('userinfo')

        if not user_info:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get user information from Google"
            )

        email = user_info.get('email')
        name = user_info.get('name')
        picture = user_info.get('picture')

        # Verify email domain
        if not email or not email.endswith(f"@{ALLOWED_DOMAIN}"):
            logger.warning(f"Unauthorized login attempt from: {email}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Only {ALLOWED_DOMAIN} emails are allowed."
            )

        # Create JWT access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={
                "sub": email,
                "name": name,
                "picture": picture
            },
            expires_delta=access_token_expires
        )

        # Store token in session (optional)
        request.session['access_token'] = access_token
        request.session['user_email'] = email
        request.session['user_name'] = name

        logger.info(f"✅ User logged in successfully: {email}")

        # Redirect to frontend with token
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(
            url=f"{frontend_url}?token={access_token}",
            status_code=status.HTTP_303_SEE_OTHER
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth callback error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed. Please try again."
        )


@router.get("/logout")
async def logout(request: Request):
    """
    Logout endpoint
    Clears session
    """
    request.session.clear()

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

    logger.info("User logged out")

    return RedirectResponse(
        url=frontend_url,
        status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/token", response_model=Token)
async def create_token_for_testing(request: Request, email: str, password: str = "test"):
    """
    DEVELOPMENT ONLY: Create token for testing without OAuth
    DO NOT USE IN PRODUCTION

    Usage: POST /auth/token?email=user@nubemsystems.es&password=test
    """
    if os.getenv("NODE_ENV") == "production":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found"
        )

    # Verify domain
    if not email.endswith(f"@{ALLOWED_DOMAIN}"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only {ALLOWED_DOMAIN} emails are allowed"
        )

    # Create token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": email},
        expires_delta=access_token_expires
    )

    logger.warning(f"⚠️  DEV MODE: Created test token for {email}")

    return Token(
        access_token=access_token,
        token_type="bearer"
    )

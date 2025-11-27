#!/usr/bin/env python3
"""
NubemSuperFClaude - Secrets Management Web API
FastAPI REST API for multi-tenant secrets management
"""

import os
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from jose import JWTError, jwt

# Import secrets manager
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.secrets_manager import secrets_manager

# Setup templates
BASE_DIR = Path(__file__).parent.parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
SECRET_KEY = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
ALLOWED_DOMAIN = os.getenv("ALLOWED_EMAIL_DOMAIN", "nubemsystems.es")

# Initialize FastAPI app
app = FastAPI(
    title="NubemSuperFClaude Secrets API",
    description="Multi-tenant secrets management API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8080").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/token", auto_error=False)


# ===== Pydantic Models =====

class SecretCreate(BaseModel):
    """Model for creating a secret"""
    name: str = Field(..., min_length=1, max_length=100, description="Secret name")
    value: str = Field(..., min_length=1, description="Secret value")
    labels: Optional[Dict[str, str]] = Field(default=None, description="Optional labels")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "my-api-key",
                "value": "sk-1234567890",
                "labels": {"env": "production", "service": "api"}
            }
        }


class SecretUpdate(BaseModel):
    """Model for updating a secret"""
    value: str = Field(..., min_length=1, description="New secret value")

    class Config:
        json_schema_extra = {
            "example": {
                "value": "sk-new-value-9876543210"
            }
        }


class SecretResponse(BaseModel):
    """Model for secret response (without value)"""
    name: str
    created_at: Optional[str] = None
    labels: Optional[Dict[str, str]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "name": "my-api-key",
                "created_at": "2025-10-01T12:00:00Z",
                "labels": {"env": "production"}
            }
        }


class SecretValueResponse(BaseModel):
    """Model for secret value response"""
    name: str
    value: str

    class Config:
        json_schema_extra = {
            "example": {
                "name": "my-api-key",
                "value": "sk-1234567890"
            }
        }


class UserInfo(BaseModel):
    """User information from token"""
    email: EmailStr
    name: Optional[str] = None
    picture: Optional[str] = None


class Token(BaseModel):
    """JWT token response"""
    access_token: str
    token_type: str


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: str
    version: str
    secret_manager_enabled: bool


# ===== Authentication =====

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> Optional[UserInfo]:
    """
    Get current user from JWT token
    Returns None if no token (for public endpoints)
    Raises HTTPException if token is invalid
    """
    if not token:
        return None

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception

        user = UserInfo(
            email=email,
            name=payload.get("name"),
            picture=payload.get("picture")
        )

        # Verify domain restriction
        if not email.endswith(f"@{ALLOWED_DOMAIN}"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Only {ALLOWED_DOMAIN} emails are allowed"
            )

        return user
    except JWTError:
        raise credentials_exception


async def require_user(user: Optional[UserInfo] = Depends(get_current_user)) -> UserInfo:
    """Require authenticated user"""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# ===== API Endpoints =====

@app.get("/health", response_model=HealthResponse)
@limiter.limit("60/minute")
async def health_check(request: Request):
    """Health check endpoint"""
    config = secrets_manager.get_configuration_info()

    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat() + "Z",
        version="1.0.0",
        secret_manager_enabled=config.get("secret_manager_enabled", False)
    )


@app.get("/api/v1/secrets")
@limiter.limit("100/15minutes")
async def list_secrets(
    request: Request,
    user: UserInfo = Depends(require_user)
):
    """
    List all secrets for the current user
    Returns JSON by default, HTML if requested by htmx
    """
    try:
        secret_names = secrets_manager.list_secrets(user_email=user.email)

        # Build secret list with metadata
        secrets_list = []
        for name in secret_names:
            secrets_list.append({
                "name": name,
                "created_at": None,  # We don't have this info from list
                "labels": None
            })

        # Check if request is from htmx
        if request.headers.get("HX-Request"):
            # Return HTML template for htmx
            return templates.TemplateResponse(
                "secrets.html",
                {
                    "request": request,
                    "secrets": secrets_list
                },
                media_type="text/html"
            )

        # Return JSON for API calls
        return [
            SecretResponse(name=name)
            for name in secret_names
        ]

    except Exception as e:
        logger.error(f"Error listing secrets for {user.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list secrets: {str(e)}"
        )


@app.get("/api/v1/secrets/{secret_name}", response_model=SecretValueResponse)
@limiter.limit("100/15minutes")
async def get_secret(
    secret_name: str,
    request: Request,
    user: UserInfo = Depends(require_user)
):
    """
    Get a specific secret value
    """
    try:
        secret_value = secrets_manager.get_secret(secret_name, user_email=user.email)

        if secret_value is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Secret '{secret_name}' not found"
            )

        return SecretValueResponse(
            name=secret_name,
            value=secret_value
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting secret {secret_name} for {user.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get secret: {str(e)}"
        )


@app.post("/api/v1/secrets", response_model=SecretResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("50/15minutes")
async def create_secret(
    secret: SecretCreate,
    request: Request,
    user: UserInfo = Depends(require_user)
):
    """
    Create a new secret
    """
    try:
        success = secrets_manager.create_secret(
            secret_name=secret.name,
            secret_value=secret.value,
            user_email=user.email,
            labels=secret.labels
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create secret"
            )

        return SecretResponse(
            name=secret.name,
            created_at=datetime.utcnow().isoformat() + "Z",
            labels=secret.labels
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating secret {secret.name} for {user.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create secret: {str(e)}"
        )


@app.put("/api/v1/secrets/{secret_name}", response_model=SecretResponse)
@limiter.limit("50/15minutes")
async def update_secret(
    secret_name: str,
    secret: SecretUpdate,
    request: Request,
    user: UserInfo = Depends(require_user)
):
    """
    Update an existing secret (add new version)
    """
    try:
        success = secrets_manager.update_secret(
            secret_name=secret_name,
            secret_value=secret.value,
            user_email=user.email
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update secret"
            )

        return SecretResponse(
            name=secret_name,
            created_at=datetime.utcnow().isoformat() + "Z"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating secret {secret_name} for {user.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update secret: {str(e)}"
        )


@app.delete("/api/v1/secrets/{secret_name}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("50/15minutes")
async def delete_secret(
    secret_name: str,
    request: Request,
    user: UserInfo = Depends(require_user)
):
    """
    Delete a secret
    """
    try:
        success = secrets_manager.delete_secret(secret_name, user_email=user.email)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Secret '{secret_name}' not found or could not be deleted"
            )

        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting secret {secret_name} for {user.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete secret: {str(e)}"
        )


@app.get("/api/v1/me", response_model=UserInfo)
@limiter.limit("60/minute")
async def get_current_user_info(
    request: Request,
    user: UserInfo = Depends(require_user)
):
    """
    Get current user information
    """
    return user


# ===== Error Handlers =====

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Custom HTTP exception handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "status_code": exc.status_code
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """General exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "status_code": 500
        }
    )


# ===== Startup/Shutdown Events =====

@app.on_event("startup")
async def startup_event():
    """Startup event"""
    logger.info("🚀 NubemSuperFClaude Secrets API starting...")
    config = secrets_manager.get_configuration_info()
    logger.info(f"📦 Secret Manager enabled: {config.get('secret_manager_enabled')}")
    logger.info(f"📦 Project ID: {config.get('project_id')}")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event"""
    logger.info("🛑 NubemSuperFClaude Secrets API shutting down...")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8080))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info(f"Starting server on {host}:{port}")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True
    )

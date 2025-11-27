#!/usr/bin/env python3
"""
CORS Configuration Module for NubemSuperFClaude
Centralizes CORS settings for security and consistency
"""

import os
from typing import List

def get_allowed_origins() -> List[str]:
    """
    Get allowed CORS origins based on environment
    
    Returns:
        List of allowed origins
    """
    env = os.getenv('ENVIRONMENT', 'development')
    
    if env == 'production':
        # Production: Strict origins only
        return [
            "https://nubemgenesis.ai",
            "https://app.nubemgenesis.ai",
            "https://api.nubemgenesis.ai",
            "https://dashboard.nubemgenesis.ai"
        ]
    elif env == 'staging':
        # Staging: Include staging domains
        return [
            "https://staging.nubemgenesis.ai",
            "https://app-staging.nubemgenesis.ai",
            "http://localhost:3000",
            "http://localhost:8000"
        ]
    else:
        # Development: Allow local development
        return [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:8000",
            "http://localhost:8080",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8000",
            "http://localhost:5173",  # Vite
            "http://localhost:4200",  # Angular
        ]

def get_cors_config() -> dict:
    """
    Get complete CORS configuration
    
    Returns:
        Dictionary with CORS settings
    """
    return {
        "allow_origins": get_allowed_origins(),
        "allow_credentials": True,
        "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        "allow_headers": [
            "Content-Type",
            "Authorization",
            "X-Requested-With",
            "X-API-Key",
            "X-Session-ID",
            "X-Persona-ID"
        ],
        "expose_headers": [
            "X-Total-Count",
            "X-Page-Number",
            "X-Page-Size",
            "X-Rate-Limit",
            "X-Rate-Remaining"
        ],
        "max_age": 3600  # 1 hour
    }

# Singleton instance
_cors_config = None

def get_cors_middleware_config():
    """
    Get CORS config for FastAPI middleware
    """
    global _cors_config
    if _cors_config is None:
        _cors_config = get_cors_config()
    return _cors_config
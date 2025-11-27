"""
Authentication and Authorization module for NubemSuperFClaude MCP Server

Supports multiple authentication methods:
- API Key authentication (for technical users and automation)
- OAuth 2.0 / Google Sign-In (for web UI users)
- OAuth 2.0 Device Flow (for CLI and limited-input devices)
- Hybrid mode (both methods simultaneously)
"""

from .user_auth_manager import UserAuthManager, get_auth_manager
from .audit_logger import AuditLogger, get_audit_logger
from .rate_limiter import RateLimiter, get_rate_limiter
from .oauth_handler import GoogleOAuthHandler, get_oauth_handler
from .hybrid_auth import HybridAuthManager, get_hybrid_auth_manager
from .device_flow_handler import DeviceFlowOAuthHandler, generate_user_code, get_device_flow_handler
from .device_code_storage import (
    DeviceCodeStorage,
    InMemoryDeviceCodeStorage,
    RedisDeviceCodeStorage
)

__all__ = [
    "UserAuthManager",
    "get_auth_manager",
    "AuditLogger",
    "get_audit_logger",
    "RateLimiter",
    "get_rate_limiter",
    "GoogleOAuthHandler",
    "get_oauth_handler",
    "HybridAuthManager",
    "get_hybrid_auth_manager",
    "DeviceFlowOAuthHandler",
    "get_device_flow_handler",
    "generate_user_code",
    "DeviceCodeStorage",
    "InMemoryDeviceCodeStorage",
    "RedisDeviceCodeStorage",
]

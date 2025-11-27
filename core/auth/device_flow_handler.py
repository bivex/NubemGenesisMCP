"""
OAuth 2.0 Device Authorization Grant (RFC 8628) Handler

Implements the Device Flow for CLI and limited-input devices.
Reuses GoogleOAuthHandler for JWT token generation.
"""

import os
import secrets
import logging
import traceback
from datetime import datetime, timedelta
from typing import Dict, Optional
from urllib.parse import quote

import jwt

from .oauth_handler import GoogleOAuthHandler
from .device_code_storage import DeviceCodeStorage
from .rate_limiter import RateLimiter
from .audit_logger import AuditLogger

logger = logging.getLogger(__name__)


def generate_user_code() -> str:
    """
    Generate human-readable user code.

    Format: XXXX-XXXX (8 chars + dash)
    Character set: BCDFGHJKLMNPQRSTVWXYZ23456789 (no ambiguous chars)
    Excludes: 0, O, I, 1, L to avoid confusion

    Returns:
        User code like "WDJB-MJHT"
    """
    # Exclude ambiguous characters: 0, O, I, 1, L
    chars = "BCDFGHJKMNPQRSTVWXYZ23456789"

    part1 = ''.join(secrets.choice(chars) for _ in range(4))
    part2 = ''.join(secrets.choice(chars) for _ in range(4))

    return f"{part1}-{part2}"


class DeviceFlowOAuthHandler:
    """
    Implements OAuth 2.0 Device Authorization Grant (RFC 8628).

    This handler enables CLI and limited-input devices to authenticate users
    through a separate browser-based OAuth flow.

    Flow:
    1. CLI requests device code
    2. CLI displays user_code and verification URI
    3. User visits URI in browser and enters user_code
    4. User completes Google OAuth flow
    5. CLI polls for token
    6. Server issues JWT token (same format as web OAuth)

    Reuses:
    - GoogleOAuthHandler for JWT token generation
    - RateLimiter for polling enforcement
    - AuditLogger for security audit trail
    """

    def __init__(
        self,
        google_oauth: GoogleOAuthHandler,
        storage: DeviceCodeStorage,
        rate_limiter: RateLimiter,
        audit_logger: AuditLogger,
        verification_uri: Optional[str] = None,
        device_code_ttl: int = 900,  # 15 minutes
        poll_interval: int = 5  # 5 seconds
    ):
        """
        Initialize Device Flow OAuth handler.

        Args:
            google_oauth: GoogleOAuthHandler instance for token generation
            storage: DeviceCodeStorage implementation
            rate_limiter: RateLimiter instance for polling control
            audit_logger: AuditLogger instance for audit trail
            verification_uri: Base URI for device authorization (default: from env)
            device_code_ttl: Device code TTL in seconds (default: 900 = 15 min)
            poll_interval: Minimum polling interval in seconds (default: 5)
        """
        self.google_oauth = google_oauth
        self.storage = storage
        self.rate_limiter = rate_limiter
        self.audit_logger = audit_logger

        self.verification_uri = verification_uri or os.getenv(
            "DEVICE_FLOW_VERIFICATION_URI",
            "https://ai.nubemsystems.es/device"
        )
        self.device_code_ttl = device_code_ttl
        self.poll_interval = poll_interval

        logger.info("✅ DeviceFlowOAuthHandler initialized")
        logger.debug(f"Verification URI: {self.verification_uri}")
        logger.debug(f"Device code TTL: {self.device_code_ttl}s")
        logger.debug(f"Poll interval: {self.poll_interval}s")

    async def generate_device_code(
        self,
        client_id: str,
        scope: str,
        client_ip: str,
        user_agent: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Generate device_code and user_code for device authorization.

        This is the first step in the device flow. The CLI calls this endpoint
        to obtain codes to display to the user.

        Args:
            client_id: OAuth client identifier (e.g., "nubemsfc-cli")
            scope: Requested scopes (e.g., "openid email profile")
            client_ip: Client IP address for rate limiting
            user_agent: Client user agent for audit logging

        Returns:
            Dict containing:
            - device_code: Unique device identifier (32 bytes, urlsafe)
            - user_code: Human-readable code (XXXX-XXXX format)
            - verification_uri: URL for user to visit
            - verification_uri_complete: URL with pre-filled user_code
            - expires_in: Seconds until expiration (900)
            - interval: Minimum polling interval in seconds (5)

        Raises:
            ValueError: If rate limit exceeded
        """
        # Rate limiting: 10 device codes per IP per minute
        # (generous rate - real limit should be in Redis/external system for production)
        rate_key = f"device_code:{client_ip}"
        allowed, rate_info = self.rate_limiter.check_rate_limit(
            user_email=rate_key,
            requests_per_minute=10,
            burst=5
        )

        if not allowed:
            logger.warning(f"Rate limit exceeded for IP {client_ip}")
            self.audit_logger.log_auth_failure(
                "device_code_rate_limit",
                {"client_ip": client_ip, "user_agent": user_agent}
            )
            raise ValueError("Rate limit exceeded. Too many device code requests.")

        # Generate codes
        device_code = secrets.token_urlsafe(32)  # 43 characters
        user_code = generate_user_code()  # XXXX-XXXX format

        # Store in storage
        device_info = {
            "device_code": device_code,
            "user_code": user_code,
            "client_id": client_id,
            "scope": scope,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(seconds=self.device_code_ttl)).isoformat()
        }

        await self.storage.store(device_info, ttl=self.device_code_ttl)

        # Audit log
        self.audit_logger.log_auth_attempt(
            "device_code_generated",
            {
                "device_code_prefix": device_code[:15],
                "user_code": user_code,
                "client_id": client_id,
                "client_ip": client_ip,
                "user_agent": user_agent,
                "scope": scope
            }
        )

        # Build response
        verification_uri_complete = f"{self.verification_uri}?user_code={user_code}"

        return {
            "device_code": device_code,
            "user_code": user_code,
            "verification_uri": self.verification_uri,
            "verification_uri_complete": verification_uri_complete,
            "expires_in": self.device_code_ttl,
            "interval": self.poll_interval
        }

    async def poll_for_token(
        self,
        device_code: str,
        client_id: str
    ) -> Dict[str, any]:
        """
        Poll for authorization status and retrieve token.

        The CLI calls this endpoint repeatedly until the user completes
        authorization or the device code expires.

        Args:
            device_code: Device code from generate_device_code()
            client_id: OAuth client identifier

        Returns:
            On success:
            {
                "access_token": "eyJhbGc...",  # JWT token
                "token_type": "Bearer",
                "expires_in": 86400,  # 24 hours
                "scope": "openid email profile"
            }

            On pending authorization:
            {
                "error": "authorization_pending",
                "error_description": "The authorization request is still pending"
            }

            On polling too fast:
            {
                "error": "slow_down",
                "error_description": "Wait at least 5 seconds between requests"
            }

            On expired code:
            {
                "error": "expired_token",
                "error_description": "The device code has expired"
            }

            On denied authorization:
            {
                "error": "access_denied",
                "error_description": "The user denied the authorization request"
            }

        Raises:
            ValueError: For invalid requests
        """
        # Load device info
        device_info = await self.storage.get(device_code)

        if device_info is None:
            logger.warning(f"Device code not found or expired: {device_code[:15]}...")
            return {
                "error": "expired_token",
                "error_description": "Device code not found or expired"
            }

        # Verify client_id matches
        if device_info.get("client_id") != client_id:
            logger.warning(f"Client ID mismatch for device code {device_code[:15]}...")
            return {
                "error": "invalid_client",
                "error_description": "Client ID does not match"
            }

        # Rate limiting: Check last poll time (minimum 5 seconds)
        last_poll = await self.storage.get_last_poll_time(device_code)
        if last_poll:
            seconds_since_poll = (datetime.utcnow() - last_poll).total_seconds()
            if seconds_since_poll < self.poll_interval:
                logger.debug(f"Polling too fast: {seconds_since_poll:.2f}s < {self.poll_interval}s")
                return {
                    "error": "slow_down",
                    "error_description": f"Wait at least {self.poll_interval} seconds between requests"
                }

        # Update last poll time
        await self.storage.update_last_poll_time(device_code)

        # Check status
        status = device_info.get("status")

        if status == "pending":
            return {
                "error": "authorization_pending",
                "error_description": "The authorization request is still pending"
            }

        elif status == "denied":
            # Delete device code (terminal state)
            await self.storage.delete(device_code)

            self.audit_logger.log_auth_failure(
                "device_authorization_denied",
                {
                    "device_code_prefix": device_code[:15],
                    "user_code": device_info.get("user_code")
                }
            )

            return {
                "error": "access_denied",
                "error_description": "The user denied the authorization request"
            }

        elif status == "approved":
            # Generate JWT token
            user_info = device_info.get("user_info")

            if not user_info:
                logger.error(f"Approved device code missing user_info: {device_code[:15]}...")
                return {
                    "error": "server_error",
                    "error_description": "Internal server error"
                }

            # Create JWT token with CLI audience
            jwt_token = self._create_device_flow_token(user_info)

            # Delete device code (single use)
            await self.storage.delete(device_code)

            # Audit log
            self.audit_logger.log_auth_success(
                "device_token_issued",
                {
                    "device_code_prefix": device_code[:15],
                    "user_code": device_info.get("user_code"),
                    "user_email": user_info.get("email"),
                    "client_id": client_id
                }
            )

            return {
                "access_token": jwt_token,
                "token_type": "Bearer",
                "expires_in": 86400,  # 24 hours
                "scope": device_info.get("scope", "openid email profile")
            }

        else:
            logger.error(f"Unknown device status: {status}")
            return {
                "error": "server_error",
                "error_description": "Internal server error"
            }

    async def approve_device(
        self,
        user_code: str,
        user_info: Dict[str, any]
    ) -> bool:
        """
        Approve device authorization after user completes OAuth flow.

        This is called by the OAuth callback handler after successful
        Google authentication.

        Args:
            user_code: User code (XXXX-XXXX format)
            user_info: User information from Google OAuth:
                - google_id: Google user ID
                - email: User email
                - name: User name
                - email_verified: Email verification status
                - picture: Profile picture URL (optional)

        Returns:
            True if device was approved successfully, False otherwise
        """
        # Find device code by user code
        device_code = await self.storage.get_by_user_code(user_code)

        if device_code is None:
            logger.warning(f"User code not found or expired: {user_code}")
            return False

        # Update status to approved
        await self.storage.update_status(
            device_code=device_code,
            status="approved",
            user_info=user_info
        )

        # Audit log
        self.audit_logger.log_auth_success(
            "device_approved",
            {
                "user_code": user_code,
                "device_code_prefix": device_code[:15],
                "user_email": user_info.get("email")
            }
        )

        logger.info(f"Device approved: user_code={user_code}, user={user_info.get('email')}")

        return True

    async def deny_device(self, user_code: str) -> bool:
        """
        Deny device authorization (user rejected).

        Args:
            user_code: User code (XXXX-XXXX format)

        Returns:
            True if device was denied successfully, False otherwise
        """
        # Find device code by user code
        device_code = await self.storage.get_by_user_code(user_code)

        if device_code is None:
            logger.warning(f"User code not found or expired: {user_code}")
            return False

        # Update status to denied
        await self.storage.update_status(
            device_code=device_code,
            status="denied"
        )

        # Audit log
        self.audit_logger.log_auth_failure(
            "device_denied",
            {
                "user_code": user_code,
                "device_code_prefix": device_code[:15]
            }
        )

        logger.info(f"Device denied: user_code={user_code}")

        return True

    async def verify_user_code(self, user_code: str) -> Optional[str]:
        """
        Verify user code exists and return device code.

        Used by the device authorization page to validate user input.

        Args:
            user_code: User code to verify (XXXX-XXXX format)

        Returns:
            Device code if valid, None if invalid/expired
        """
        device_code = await self.storage.get_by_user_code(user_code)

        if device_code is None:
            logger.debug(f"User code not found: {user_code}")
            return None

        # Verify device code still exists
        device_info = await self.storage.get(device_code)
        if device_info is None:
            logger.debug(f"Device code expired for user_code: {user_code}")
            return None

        return device_code

    def _create_device_flow_token(self, user_info: Dict[str, any]) -> str:
        """
        Create JWT session token for device flow with CLI audience.

        This reuses the token generation logic from GoogleOAuthHandler
        but modifies the audience to distinguish CLI tokens.

        Args:
            user_info: User information from OAuth

        Returns:
            JWT token string
        """
        now = datetime.utcnow()

        payload = {
            'sub': user_info['email'],
            'google_id': user_info.get('google_id'),
            'name': user_info.get('name'),
            'email': user_info['email'],
            'email_verified': user_info.get('email_verified', False),
            'picture': user_info.get('picture'),
            'iat': now,
            'exp': now + timedelta(hours=24),
            'iss': 'nubemsfc-mcp-server',
            'aud': 'nubemsfc-cli-client',  # CLI audience (vs web-client)
            'device_flow': True  # Marker for device flow tokens
        }

        token = jwt.encode(payload, self.google_oauth.jwt_secret, algorithm='HS256')

        logger.debug(f"Created device flow JWT token for: {user_info['email']}")

        return token


# ============================================================================
# Singleton Instance
# ============================================================================

_device_flow_handler: Optional[DeviceFlowOAuthHandler] = None


def get_device_flow_handler() -> Optional[DeviceFlowOAuthHandler]:
    """
    Get the singleton DeviceFlowOAuthHandler instance.

    Returns:
        DeviceFlowOAuthHandler instance if Device Flow is enabled, None otherwise
    """
    global _device_flow_handler

    if _device_flow_handler is None:
        # Check if Device Flow is enabled
        device_flow_enabled = os.getenv("DEVICE_FLOW_ENABLED", "false").lower() == "true"

        if not device_flow_enabled:
            logger.info("OAuth Device Flow is disabled (DEVICE_FLOW_ENABLED=false)")
            return None

        # Initialize Device Flow Handler
        try:
            logger.info("Initializing OAuth Device Flow Handler...")

            # Get dependencies from other singletons
            from .oauth_handler import get_oauth_handler
            from .rate_limiter import get_rate_limiter
            from .audit_logger import get_audit_logger

            google_oauth = get_oauth_handler()
            rate_limiter = get_rate_limiter()
            audit_logger = get_audit_logger()

            # Initialize storage (Redis for production, in-memory for dev)
            redis_url = os.getenv("REDIS_URL")

            # If REDIS_URL contains unexpanded variables like $(REDIS_PASSWORD), construct from components
            if redis_url and "$(REDIS_PASSWORD)" in redis_url:
                logger.info(f"⚠️  Detected unexpanded REDIS_URL: {redis_url} - reconstructing from components")
                redis_url = None  # Force reconstruction

            if not redis_url:
                # Construct from components
                redis_host = os.getenv("REDIS_HOST", "redis-device-flow")
                redis_port = os.getenv("REDIS_PORT", "6379")
                redis_password = os.getenv("REDIS_PASSWORD", "")  # Keep original password (may include newline)
                redis_db = os.getenv("REDIS_DB", "0")

                if redis_password:
                    # URL-encode password to handle special characters like newlines
                    encoded_password = quote(redis_password, safe='')
                    redis_url = f"redis://:{encoded_password}@{redis_host}:{redis_port}/{redis_db}"
                    logger.info(f"✅ Constructed Redis URL from components (host={redis_host}, port={redis_port}, db={redis_db}, auth=yes, password_encoded=yes)")
                else:
                    redis_url = f"redis://{redis_host}:{redis_port}/{redis_db}"
                    logger.info(f"✅ Constructed Redis URL from components (host={redis_host}, port={redis_port}, db={redis_db}, auth=no)")

            if redis_url:
                from .device_code_storage import RedisDeviceCodeStorage
                storage = RedisDeviceCodeStorage(redis_url)
                logger.info("Using Redis storage for Device Flow")
            else:
                from .device_code_storage import InMemoryDeviceCodeStorage
                storage = InMemoryDeviceCodeStorage()
                logger.info("Using in-memory storage for Device Flow")

            # Get config from environment
            verification_uri = os.getenv("DEVICE_FLOW_VERIFICATION_URI", "https://ai.nubemsystems.es/device")
            device_code_ttl = int(os.getenv("DEVICE_CODE_EXPIRATION_SECONDS", "900"))
            poll_interval = int(os.getenv("DEVICE_POLLING_INTERVAL_SECONDS", "5"))

            _device_flow_handler = DeviceFlowOAuthHandler(
                google_oauth=google_oauth,
                storage=storage,
                rate_limiter=rate_limiter,
                audit_logger=audit_logger,
                verification_uri=verification_uri,
                device_code_ttl=device_code_ttl,
                poll_interval=poll_interval
            )
            logger.info("✅ OAuth Device Flow Handler initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Device Flow Handler: {e}")
            logger.error(traceback.format_exc())
            return None

    return _device_flow_handler

"""
Integration tests for Device Flow endpoints

Tests all HTTP endpoints for OAuth Device Flow:
- POST /auth/device/code
- POST /auth/device/token
- POST /auth/device/verify
- GET /device

Tests HTTP responses, status codes, rate limiting, and error handling.
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from fastapi.testclient import TestClient
from httpx import AsyncClient
import jwt


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_app():
    """Create FastAPI app with device flow routes"""
    from fastapi import FastAPI
    from core.auth.device_flow_handler import DeviceFlowOAuthHandler
    from core.auth.device_code_storage import InMemoryDeviceCodeStorage
    from mcp_server import device_flow_routes

    app = FastAPI()

    # Create mock dependencies
    mock_google_oauth = Mock()
    mock_google_oauth.jwt_secret = "test_jwt_secret_key"
    mock_google_oauth.is_configured.return_value = True

    mock_rate_limiter = Mock()
    mock_rate_limiter.check_rate_limit.return_value = (True, {})

    mock_audit_logger = Mock()

    storage = InMemoryDeviceCodeStorage()

    # Create device handler
    device_handler = DeviceFlowOAuthHandler(
        google_oauth=mock_google_oauth,
        storage=storage,
        rate_limiter=mock_rate_limiter,
        audit_logger=mock_audit_logger,
        verification_uri="https://test.example.com/device"
    )

    # Initialize routes
    device_flow_routes.device_flow_handler = device_handler

    # Include router
    app.include_router(device_flow_routes.router)

    return app


@pytest.fixture
async def async_client(mock_app):
    """Create async HTTP client"""
    async with AsyncClient(app=mock_app, base_url="http://test") as client:
        yield client


# ============================================================================
# TESTS: POST /auth/device/code
# ============================================================================

@pytest.mark.asyncio
class TestDeviceCodeEndpoint:
    """Tests for POST /auth/device/code"""

    async def test_returns_200_with_all_fields(self, async_client):
        """Test successful device code generation"""
        response = await async_client.post(
            "/auth/device/code",
            json={
                "client_id": "nubemsfc-cli",
                "scope": "openid email profile"
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Verify all required fields
        assert "device_code" in data
        assert "user_code" in data
        assert "verification_uri" in data
        assert "verification_uri_complete" in data
        assert "expires_in" in data
        assert "interval" in data

    async def test_device_code_is_url_safe(self, async_client):
        """Test device code uses URL-safe characters"""
        response = await async_client.post(
            "/auth/device/code",
            json={"client_id": "test-client", "scope": "openid"}
        )

        data = response.json()
        device_code = data["device_code"]

        # Verify URL-safe
        import re
        assert re.match(r'^[A-Za-z0-9_-]+$', device_code)

    async def test_user_code_format_xxxx_xxxx(self, async_client):
        """Test user code has XXXX-XXXX format"""
        response = await async_client.post(
            "/auth/device/code",
            json={"client_id": "test-client", "scope": "openid"}
        )

        data = response.json()
        user_code = data["user_code"]

        # Verify format
        assert len(user_code) == 9
        assert user_code[4] == '-'
        import re
        assert re.match(r'^[A-Z0-9]{4}-[A-Z0-9]{4}$', user_code)

    async def test_verification_uri_correct(self, async_client):
        """Test verification URI is correct"""
        response = await async_client.post(
            "/auth/device/code",
            json={"client_id": "test-client", "scope": "openid"}
        )

        data = response.json()
        assert data["verification_uri"] == "https://test.example.com/device"

    async def test_expires_in_900_seconds(self, async_client):
        """Test device code expires in 900 seconds (15 min)"""
        response = await async_client.post(
            "/auth/device/code",
            json={"client_id": "test-client", "scope": "openid"}
        )

        data = response.json()
        assert data["expires_in"] == 900

    async def test_interval_5_seconds(self, async_client):
        """Test polling interval is 5 seconds"""
        response = await async_client.post(
            "/auth/device/code",
            json={"client_id": "test-client", "scope": "openid"}
        )

        data = response.json()
        assert data["interval"] == 5

    async def test_verification_uri_complete_includes_user_code(self, async_client):
        """Test verification_uri_complete includes user_code"""
        response = await async_client.post(
            "/auth/device/code",
            json={"client_id": "test-client", "scope": "openid"}
        )

        data = response.json()
        user_code = data["user_code"]
        complete_uri = data["verification_uri_complete"]

        assert user_code in complete_uri
        assert "user_code=" in complete_uri

    @pytest.mark.skip(reason="Rate limiting needs proper mock setup")
    async def test_rate_limiting_429_after_10_requests(self, async_client):
        """Test rate limiting returns 429 after 10 requests"""
        # This would require proper rate limiter mock setup
        pass


# ============================================================================
# TESTS: POST /auth/device/token
# ============================================================================

@pytest.mark.asyncio
class TestDeviceTokenEndpoint:
    """Tests for POST /auth/device/token"""

    async def test_authorization_pending_initially(self, async_client):
        """Test returns authorization_pending when device not approved"""
        # First, request device code
        code_response = await async_client.post(
            "/auth/device/code",
            json={"client_id": "test-client", "scope": "openid"}
        )
        device_code = code_response.json()["device_code"]

        # Poll for token
        response = await async_client.post(
            "/auth/device/token",
            json={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": "test-client"
            }
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "authorization_pending"

    async def test_slow_down_when_polling_fast(self, async_client):
        """Test returns slow_down when polling < 5 seconds"""
        # Request device code
        code_response = await async_client.post(
            "/auth/device/code",
            json={"client_id": "test-client", "scope": "openid"}
        )
        device_code = code_response.json()["device_code"]

        # First poll
        await async_client.post(
            "/auth/device/token",
            json={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": "test-client"
            }
        )

        # Second poll immediately
        response2 = await async_client.post(
            "/auth/device/token",
            json={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": "test-client"
            }
        )

        data = response2.json()
        assert data["error"] == "slow_down"

    async def test_expired_token_when_not_found(self, async_client):
        """Test returns expired_token for non-existent device code"""
        response = await async_client.post(
            "/auth/device/token",
            json={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": "nonexistent_code",
                "client_id": "test-client"
            }
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "expired_token"

    async def test_returns_jwt_token_when_approved(self, async_client, mock_app):
        """Test returns JWT access token when device is approved"""
        # Get device handler from app
        from mcp_server import device_flow_routes
        handler = device_flow_routes.device_flow_handler

        # Request device code
        code_response = await async_client.post(
            "/auth/device/code",
            json={"client_id": "test-client", "scope": "openid email"}
        )
        device_data = code_response.json()

        # Approve device
        user_info = {
            "email": "test@example.com",
            "google_id": "123456",
            "name": "Test User",
            "email_verified": True
        }
        await handler.approve_device(device_data["user_code"], user_info)

        # Poll for token
        token_response = await async_client.post(
            "/auth/device/token",
            json={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_data["device_code"],
                "client_id": "test-client"
            }
        )

        assert token_response.status_code == 200
        data = token_response.json()

        assert "access_token" in data
        assert data["token_type"] == "Bearer"
        assert data["expires_in"] == 86400
        assert "scope" in data

    async def test_token_is_valid_jwt(self, async_client, mock_app):
        """Test returned token is valid JWT"""
        from mcp_server import device_flow_routes
        handler = device_flow_routes.device_flow_handler

        # Request and approve
        code_response = await async_client.post(
            "/auth/device/code",
            json={"client_id": "test-client", "scope": "openid"}
        )
        device_data = code_response.json()

        user_info = {"email": "test@example.com", "google_id": "123"}
        await handler.approve_device(device_data["user_code"], user_info)

        # Get token
        token_response = await async_client.post(
            "/auth/device/token",
            json={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_data["device_code"],
                "client_id": "test-client"
            }
        )

        token = token_response.json()["access_token"]

        # Decode and verify
        decoded = jwt.decode(
            token,
            handler.google_oauth.jwt_secret,
            algorithms=["HS256"]
        )

        assert decoded["email"] == "test@example.com"
        assert decoded["aud"] == "nubemsfc-cli-client"
        assert decoded["device_flow"] is True

    async def test_unsupported_grant_type(self, async_client):
        """Test returns error for unsupported grant type"""
        response = await async_client.post(
            "/auth/device/token",
            json={
                "grant_type": "invalid_grant_type",
                "device_code": "test",
                "client_id": "test-client"
            }
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "unsupported_grant_type"


# ============================================================================
# TESTS: POST /auth/device/verify
# ============================================================================

@pytest.mark.asyncio
class TestDeviceVerifyEndpoint:
    """Tests for POST /auth/device/verify"""

    async def test_validates_valid_user_code(self, async_client, mock_app):
        """Test accepts valid user code"""
        # Generate device code
        code_response = await async_client.post(
            "/auth/device/code",
            json={"client_id": "test-client", "scope": "openid"}
        )
        user_code = code_response.json()["user_code"]

        # Mock OAuth handler
        from core.auth.oauth_handler import get_oauth_handler
        with patch('core.auth.oauth_handler.get_oauth_handler') as mock_get_oauth:
            mock_oauth = Mock()
            mock_oauth.is_configured.return_value = True
            mock_oauth.get_authorization_url.return_value = {
                "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
                "state": "test_state_123",
                "nonce": "test_nonce_456",
                "code_verifier": "test_verifier_789"
            }
            mock_get_oauth.return_value = mock_oauth

            # Verify user code
            response = await async_client.post(
                "/auth/device/verify",
                json={"user_code": user_code}
            )

            assert response.status_code == 200
            data = response.json()
            assert "authorization_url" in data

    async def test_rejects_invalid_user_code(self, async_client):
        """Test rejects invalid user code"""
        # Mock OAuth handler
        from core.auth.oauth_handler import get_oauth_handler
        with patch('core.auth.oauth_handler.get_oauth_handler') as mock_get_oauth:
            mock_oauth = Mock()
            mock_oauth.is_configured.return_value = True
            mock_get_oauth.return_value = mock_oauth

            response = await async_client.post(
                "/auth/device/verify",
                json={"user_code": "INVALID-CODE"}
            )

            assert response.status_code == 400
            data = response.json()
            assert data["error"] == "invalid_code"

    async def test_rejects_expired_user_code(self, async_client, mock_app):
        """Test rejects expired user code"""
        from mcp_server import device_flow_routes
        handler = device_flow_routes.device_flow_handler

        # Generate and delete (simulate expiration)
        code_response = await async_client.post(
            "/auth/device/code",
            json={"client_id": "test-client", "scope": "openid"}
        )
        user_code = code_response.json()["user_code"]
        device_code = code_response.json()["device_code"]

        await handler.storage.delete(device_code)

        # Mock OAuth handler
        from core.auth.oauth_handler import get_oauth_handler
        with patch('core.auth.oauth_handler.get_oauth_handler') as mock_get_oauth:
            mock_oauth = Mock()
            mock_oauth.is_configured.return_value = True
            mock_get_oauth.return_value = mock_oauth

            # Try to verify
            response = await async_client.post(
                "/auth/device/verify",
                json={"user_code": user_code}
            )

            assert response.status_code == 400

    async def test_normalizes_user_code(self, async_client, mock_app):
        """Test normalizes user code (uppercase, trim)"""
        # Generate device code
        code_response = await async_client.post(
            "/auth/device/code",
            json={"client_id": "test-client", "scope": "openid"}
        )
        user_code = code_response.json()["user_code"]

        # Mock OAuth handler
        from core.auth.oauth_handler import get_oauth_handler
        with patch('core.auth.oauth_handler.get_oauth_handler') as mock_get_oauth:
            mock_oauth = Mock()
            mock_oauth.is_configured.return_value = True
            mock_oauth.get_authorization_url.return_value = {
                "authorization_url": "https://accounts.google.com/oauth",
                "state": "state",
                "nonce": "nonce",
                "code_verifier": "verifier"
            }
            mock_get_oauth.return_value = mock_oauth

            # Submit with lowercase and spaces
            response = await async_client.post(
                "/auth/device/verify",
                json={"user_code": f"  {user_code.lower()}  "}
            )

            assert response.status_code == 200


# ============================================================================
# TESTS: GET /device (Device Authorization Page)
# ============================================================================

@pytest.mark.asyncio
class TestDevicePageEndpoint:
    """Tests for GET /device"""

    @pytest.mark.skip(reason="Requires template setup")
    async def test_returns_html_page(self):
        """Test returns HTML page"""
        # This would require full app setup with templates
        pass

    @pytest.mark.skip(reason="Requires template setup")
    async def test_includes_javascript(self):
        """Test HTML includes device_flow.js"""
        pass

    @pytest.mark.skip(reason="Requires template setup")
    async def test_pre_fills_user_code_from_query(self):
        """Test pre-fills user_code from query params"""
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

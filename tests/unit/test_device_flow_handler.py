"""
Unit tests for DeviceFlowOAuthHandler

Tests all methods of the Device Flow handler including:
- Device code generation
- Token polling
- Device approval/denial
- User code verification
- Rate limiting
- JWT token creation
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
import jwt
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from core.auth.device_flow_handler import (
    DeviceFlowOAuthHandler,
    generate_user_code
)
from core.auth.device_code_storage import InMemoryDeviceCodeStorage


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_google_oauth():
    """Mock GoogleOAuthHandler"""
    mock = Mock()
    mock.jwt_secret = "test_jwt_secret_key_123456789"
    mock.is_configured.return_value = True
    return mock


@pytest.fixture
def mock_storage():
    """Mock DeviceCodeStorage"""
    return InMemoryDeviceCodeStorage()


@pytest.fixture
def mock_rate_limiter():
    """Mock RateLimiter"""
    mock = Mock()
    mock.check_rate_limit.return_value = (True, {
        "current_count": 0,
        "limit": 10,
        "window_seconds": 3600
    })
    return mock


@pytest.fixture
def mock_audit_logger():
    """Mock AuditLogger"""
    mock = Mock()
    mock.log_auth_attempt = Mock()
    mock.log_auth_success = Mock()
    mock.log_auth_failure = Mock()
    return mock


@pytest.fixture
async def device_handler(mock_google_oauth, mock_storage, mock_rate_limiter, mock_audit_logger):
    """Create DeviceFlowOAuthHandler instance"""
    handler = DeviceFlowOAuthHandler(
        google_oauth=mock_google_oauth,
        storage=mock_storage,
        rate_limiter=mock_rate_limiter,
        audit_logger=mock_audit_logger,
        verification_uri="https://test.example.com/device",
        device_code_ttl=900,
        poll_interval=5
    )
    return handler


# ============================================================================
# TESTS: generate_user_code()
# ============================================================================

class TestGenerateUserCode:
    """Tests for generate_user_code() function"""

    def test_format_is_correct(self):
        """Test user code has XXXX-XXXX format"""
        code = generate_user_code()
        assert len(code) == 9
        assert code[4] == '-'
        assert code[:4].isalnum()
        assert code[5:].isalnum()

    def test_no_ambiguous_chars(self):
        """Test no ambiguous characters (0, O, I, 1, L)"""
        ambiguous = {'0', 'O', 'I', '1', 'L', 'o', 'i', 'l'}
        codes = [generate_user_code() for _ in range(100)]
        all_chars = ''.join(codes)

        for char in ambiguous:
            assert char not in all_chars, f"Found ambiguous char: {char}"

    def test_uniqueness(self):
        """Test generated codes are reasonably unique"""
        codes = [generate_user_code() for _ in range(100)]
        unique_codes = set(codes)
        # Allow for some collisions but expect >95% unique
        assert len(unique_codes) > 95

    def test_uppercase_only(self):
        """Test all characters are uppercase"""
        codes = [generate_user_code() for _ in range(50)]
        for code in codes:
            clean_code = code.replace('-', '')
            assert clean_code.isupper()


# ============================================================================
# TESTS: DeviceFlowOAuthHandler.generate_device_code()
# ============================================================================

@pytest.mark.asyncio
class TestGenerateDeviceCode:
    """Tests for generate_device_code() method"""

    async def test_generates_valid_device_code(self, device_handler):
        """Test device code generation returns all required fields"""
        result = await device_handler.generate_device_code(
            client_id="test-client",
            scope="openid email",
            client_ip="192.168.1.1",
            user_agent="TestAgent/1.0"
        )

        # Verify all required fields
        assert "device_code" in result
        assert "user_code" in result
        assert "verification_uri" in result
        assert "verification_uri_complete" in result
        assert "expires_in" in result
        assert "interval" in result

        # Verify field values
        assert len(result["device_code"]) == 43  # URL-safe 32 bytes
        assert len(result["user_code"]) == 9  # XXXX-XXXX
        assert result["verification_uri"] == "https://test.example.com/device"
        assert result["user_code"] in result["verification_uri_complete"]
        assert result["expires_in"] == 900
        assert result["interval"] == 5

    async def test_device_code_is_url_safe(self, device_handler):
        """Test device code uses URL-safe characters"""
        result = await device_handler.generate_device_code(
            client_id="test-client",
            scope="openid",
            client_ip="127.0.0.1"
        )

        device_code = result["device_code"]
        # URL-safe characters: A-Za-z0-9_-
        import re
        assert re.match(r'^[A-Za-z0-9_-]+$', device_code)

    async def test_stores_in_storage(self, device_handler, mock_storage):
        """Test device code is stored in storage"""
        result = await device_handler.generate_device_code(
            client_id="test-client",
            scope="openid",
            client_ip="127.0.0.1"
        )

        # Verify stored in storage
        device_info = await mock_storage.get(result["device_code"])
        assert device_info is not None
        assert device_info["user_code"] == result["user_code"]
        assert device_info["client_id"] == "test-client"
        assert device_info["status"] == "pending"

    async def test_rate_limiting_enforced(self, device_handler, mock_rate_limiter):
        """Test rate limiting is enforced"""
        # Mock rate limit exceeded
        mock_rate_limiter.check_rate_limit.return_value = (False, {
            "current_count": 10,
            "limit": 10,
            "window_seconds": 3600
        })

        with pytest.raises(ValueError, match="Rate limit exceeded"):
            await device_handler.generate_device_code(
                client_id="test-client",
                scope="openid",
                client_ip="192.168.1.1"
            )

    async def test_audit_logging(self, device_handler, mock_audit_logger):
        """Test audit logging is performed"""
        await device_handler.generate_device_code(
            client_id="test-client",
            scope="openid",
            client_ip="192.168.1.1",
            user_agent="TestAgent/1.0"
        )

        # Verify audit log was called
        mock_audit_logger.log_auth_attempt.assert_called_once()
        call_args = mock_audit_logger.log_auth_attempt.call_args[0]
        assert call_args[0] == "device_code_generated"


# ============================================================================
# TESTS: DeviceFlowOAuthHandler.poll_for_token()
# ============================================================================

@pytest.mark.asyncio
class TestPollForToken:
    """Tests for poll_for_token() method"""

    async def test_authorization_pending(self, device_handler):
        """Test returns authorization_pending when still waiting"""
        # Generate device code
        result = await device_handler.generate_device_code(
            client_id="test-client",
            scope="openid",
            client_ip="127.0.0.1"
        )

        # Poll immediately
        poll_result = await device_handler.poll_for_token(
            device_code=result["device_code"],
            client_id="test-client"
        )

        assert "error" in poll_result
        assert poll_result["error"] == "authorization_pending"

    async def test_slow_down_when_polling_too_fast(self, device_handler):
        """Test returns slow_down when polling < 5 seconds"""
        # Generate device code
        result = await device_handler.generate_device_code(
            client_id="test-client",
            scope="openid",
            client_ip="127.0.0.1"
        )

        # First poll - should succeed with authorization_pending
        poll1 = await device_handler.poll_for_token(
            device_code=result["device_code"],
            client_id="test-client"
        )
        assert poll1["error"] == "authorization_pending"

        # Second poll immediately - should get slow_down
        poll2 = await device_handler.poll_for_token(
            device_code=result["device_code"],
            client_id="test-client"
        )
        assert poll2["error"] == "slow_down"

    async def test_expired_token(self, device_handler, mock_storage):
        """Test returns expired_token when device code not found"""
        # Poll with non-existent device code
        result = await device_handler.poll_for_token(
            device_code="nonexistent_device_code",
            client_id="test-client"
        )

        assert result["error"] == "expired_token"

    async def test_access_denied_when_denied(self, device_handler):
        """Test returns access_denied when user denies"""
        # Generate and deny device
        result = await device_handler.generate_device_code(
            client_id="test-client",
            scope="openid",
            client_ip="127.0.0.1"
        )

        await device_handler.deny_device(result["user_code"])

        # Poll should return access_denied
        poll_result = await device_handler.poll_for_token(
            device_code=result["device_code"],
            client_id="test-client"
        )

        assert poll_result["error"] == "access_denied"

    async def test_returns_token_when_approved(self, device_handler):
        """Test returns JWT token when approved"""
        # Generate device code
        result = await device_handler.generate_device_code(
            client_id="test-client",
            scope="openid email",
            client_ip="127.0.0.1"
        )

        # Approve device
        user_info = {
            "google_id": "123456",
            "email": "test@example.com",
            "name": "Test User",
            "email_verified": True
        }
        await device_handler.approve_device(result["user_code"], user_info)

        # Poll should return token
        poll_result = await device_handler.poll_for_token(
            device_code=result["device_code"],
            client_id="test-client"
        )

        assert "access_token" in poll_result
        assert poll_result["token_type"] == "Bearer"
        assert poll_result["expires_in"] == 86400
        assert poll_result["scope"] == "openid email"

        # Verify JWT token
        token = poll_result["access_token"]
        decoded = jwt.decode(
            token,
            device_handler.google_oauth.jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False, "verify_exp": False}
        )
        assert decoded["email"] == "test@example.com"
        assert decoded["aud"] == "nubemsfc-cli-client"
        assert decoded["device_flow"] is True

    async def test_device_code_deleted_after_token_issued(self, device_handler, mock_storage):
        """Test device code is deleted after token is issued (single-use)"""
        # Generate and approve device
        result = await device_handler.generate_device_code(
            client_id="test-client",
            scope="openid",
            client_ip="127.0.0.1"
        )

        user_info = {
            "email": "test@example.com",
            "google_id": "123"
        }
        await device_handler.approve_device(result["user_code"], user_info)

        # Poll for token
        await device_handler.poll_for_token(
            device_code=result["device_code"],
            client_id="test-client"
        )

        # Device code should be deleted
        device_info = await mock_storage.get(result["device_code"])
        assert device_info is None

    async def test_client_id_mismatch(self, device_handler):
        """Test returns error when client_id doesn't match"""
        # Generate device code
        result = await device_handler.generate_device_code(
            client_id="original-client",
            scope="openid",
            client_ip="127.0.0.1"
        )

        # Poll with different client_id
        poll_result = await device_handler.poll_for_token(
            device_code=result["device_code"],
            client_id="different-client"
        )

        assert poll_result["error"] == "invalid_client"


# ============================================================================
# TESTS: DeviceFlowOAuthHandler.approve_device()
# ============================================================================

@pytest.mark.asyncio
class TestApproveDevice:
    """Tests for approve_device() method"""

    async def test_approves_device_successfully(self, device_handler, mock_storage):
        """Test device is approved and status updated"""
        # Generate device code
        result = await device_handler.generate_device_code(
            client_id="test-client",
            scope="openid",
            client_ip="127.0.0.1"
        )

        # Approve device
        user_info = {
            "email": "test@example.com",
            "google_id": "123456"
        }
        success = await device_handler.approve_device(result["user_code"], user_info)

        assert success is True

        # Verify status updated
        device_info = await mock_storage.get(result["device_code"])
        assert device_info["status"] == "approved"
        assert device_info["user_info"]["email"] == "test@example.com"

    async def test_returns_false_for_invalid_user_code(self, device_handler):
        """Test returns False for non-existent user code"""
        success = await device_handler.approve_device(
            user_code="FAKE-CODE",
            user_info={"email": "test@example.com"}
        )

        assert success is False

    async def test_audit_logging_on_approval(self, device_handler, mock_audit_logger):
        """Test audit logging on device approval"""
        # Generate and approve
        result = await device_handler.generate_device_code(
            client_id="test-client",
            scope="openid",
            client_ip="127.0.0.1"
        )

        user_info = {"email": "test@example.com", "google_id": "123"}
        await device_handler.approve_device(result["user_code"], user_info)

        # Verify audit log
        mock_audit_logger.log_auth_success.assert_called()


# ============================================================================
# TESTS: DeviceFlowOAuthHandler.verify_user_code()
# ============================================================================

@pytest.mark.asyncio
class TestVerifyUserCode:
    """Tests for verify_user_code() method"""

    async def test_validates_correct_user_code(self, device_handler):
        """Test valid user code is accepted"""
        # Generate device code
        result = await device_handler.generate_device_code(
            client_id="test-client",
            scope="openid",
            client_ip="127.0.0.1"
        )

        # Verify user code
        device_code = await device_handler.verify_user_code(result["user_code"])

        assert device_code is not None
        assert device_code == result["device_code"]

    async def test_rejects_invalid_user_code(self, device_handler):
        """Test invalid user code is rejected"""
        device_code = await device_handler.verify_user_code("FAKE-CODE")
        assert device_code is None

    async def test_rejects_expired_user_code(self, device_handler, mock_storage):
        """Test expired user code is rejected"""
        # Generate device code
        result = await device_handler.generate_device_code(
            client_id="test-client",
            scope="openid",
            client_ip="127.0.0.1"
        )

        # Delete device code (simulate expiration)
        await mock_storage.delete(result["device_code"])

        # Verify should fail
        device_code = await device_handler.verify_user_code(result["user_code"])
        assert device_code is None


# ============================================================================
# TESTS: JWT Token Creation
# ============================================================================

@pytest.mark.asyncio
class TestJWTTokenCreation:
    """Tests for JWT token creation"""

    async def test_jwt_has_correct_audience(self, device_handler):
        """Test JWT token has CLI audience"""
        result = await device_handler.generate_device_code(
            client_id="test-client",
            scope="openid",
            client_ip="127.0.0.1"
        )

        user_info = {
            "email": "test@example.com",
            "google_id": "123",
            "name": "Test User",
            "email_verified": True
        }
        await device_handler.approve_device(result["user_code"], user_info)

        poll_result = await device_handler.poll_for_token(
            device_code=result["device_code"],
            client_id="test-client"
        )

        token = poll_result["access_token"]
        decoded = jwt.decode(
            token,
            device_handler.google_oauth.jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False, "verify_exp": False}
        )

        # Verify CLI audience (not web-client)
        assert decoded["aud"] == "nubemsfc-cli-client"

    async def test_jwt_has_device_flow_marker(self, device_handler):
        """Test JWT token has device_flow marker"""
        result = await device_handler.generate_device_code(
            client_id="test-client",
            scope="openid",
            client_ip="127.0.0.1"
        )

        user_info = {"email": "test@example.com", "google_id": "123"}
        await device_handler.approve_device(result["user_code"], user_info)

        poll_result = await device_handler.poll_for_token(
            device_code=result["device_code"],
            client_id="test-client"
        )

        token = poll_result["access_token"]
        decoded = jwt.decode(
            token,
            device_handler.google_oauth.jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False, "verify_exp": False}
        )

        assert "device_flow" in decoded
        assert decoded["device_flow"] is True

    async def test_jwt_expiration_is_24_hours(self, device_handler):
        """Test JWT token expires in 24 hours"""
        result = await device_handler.generate_device_code(
            client_id="test-client",
            scope="openid",
            client_ip="127.0.0.1"
        )

        user_info = {"email": "test@example.com", "google_id": "123"}
        await device_handler.approve_device(result["user_code"], user_info)

        poll_result = await device_handler.poll_for_token(
            device_code=result["device_code"],
            client_id="test-client"
        )

        token = poll_result["access_token"]
        decoded = jwt.decode(
            token,
            device_handler.google_oauth.jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False, "verify_exp": False}
        )

        # Verify 24 hour expiration
        exp_time = datetime.fromtimestamp(decoded["exp"])
        iat_time = datetime.fromtimestamp(decoded["iat"])
        delta = exp_time - iat_time

        # Should be approximately 24 hours (86400 seconds)
        assert 86300 <= delta.total_seconds() <= 86500


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

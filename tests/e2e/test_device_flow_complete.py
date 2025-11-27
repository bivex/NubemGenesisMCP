"""
End-to-End tests for complete Device Flow

Simulates the complete device authorization flow:
1. CLI requests device code
2. User opens /device in browser
3. User enters user_code
4. System redirects to Google OAuth (mocked)
5. Google callback approves device
6. CLI polls and obtains token
7. CLI uses token to call MCP

Tests the full integration of all components.
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
import sys
import os
import jwt

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from core.auth.device_flow_handler import DeviceFlowOAuthHandler
from core.auth.device_code_storage import InMemoryDeviceCodeStorage


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_google_oauth():
    """Mock GoogleOAuthHandler"""
    mock = Mock()
    mock.jwt_secret = "test_jwt_secret_key_for_e2e_testing"
    mock.is_configured.return_value = True
    mock.get_authorization_url.return_value = {
        "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
        "state": "test_oauth_state_123",
        "nonce": "test_nonce_456",
        "code_verifier": "test_verifier_789"
    }
    return mock


@pytest.fixture
def storage():
    """Create InMemoryDeviceCodeStorage"""
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
    return mock


@pytest.fixture
def device_handler(mock_google_oauth, storage, mock_rate_limiter, mock_audit_logger):
    """Create DeviceFlowOAuthHandler"""
    return DeviceFlowOAuthHandler(
        google_oauth=mock_google_oauth,
        storage=storage,
        rate_limiter=mock_rate_limiter,
        audit_logger=mock_audit_logger,
        verification_uri="https://ai.nubemsystems.es/device"
    )


# ============================================================================
# SCENARIO 1: Happy Path - Complete Flow
# ============================================================================

@pytest.mark.asyncio
async def test_complete_device_flow_happy_path(device_handler):
    """
    Test complete device flow - happy path

    Flow:
    1. CLI requests device code
    2. CLI displays user_code to user
    3. User enters code in browser
    4. User completes OAuth (mocked)
    5. Device is approved
    6. CLI polls and gets token
    7. Token is valid JWT
    """

    # STEP 1: CLI requests device code
    print("\n[STEP 1] CLI requests device code...")
    device_code_response = await device_handler.generate_device_code(
        client_id="nubemsfc-cli",
        scope="openid email profile",
        client_ip="192.168.1.100",
        user_agent="NubemSFC-CLI/1.0"
    )

    assert "device_code" in device_code_response
    assert "user_code" in device_code_response

    device_code = device_code_response["device_code"]
    user_code = device_code_response["user_code"]

    print(f"  ✓ Device code generated: {device_code[:15]}...")
    print(f"  ✓ User code: {user_code}")

    # STEP 2: CLI displays code to user (simulated)
    print(f"\n[STEP 2] CLI displays:")
    print(f"  Go to: {device_code_response['verification_uri']}")
    print(f"  Enter code: {user_code}")

    # STEP 3: User enters code in browser (verify it's valid)
    print(f"\n[STEP 3] User enters code in browser...")
    verified_device_code = await device_handler.verify_user_code(user_code)
    assert verified_device_code == device_code
    print(f"  ✓ User code verified")

    # STEP 4: User completes OAuth (mocked - in real flow this happens via Google)
    print(f"\n[STEP 4] User completes Google OAuth...")
    user_info = {
        "google_id": "123456789",
        "email": "user@example.com",
        "name": "Test User",
        "email_verified": True,
        "picture": "https://example.com/photo.jpg"
    }
    print(f"  ✓ OAuth completed for: {user_info['email']}")

    # STEP 5: Device is approved
    print(f"\n[STEP 5] Approving device...")
    approval_success = await device_handler.approve_device(user_code, user_info)
    assert approval_success is True
    print(f"  ✓ Device approved")

    # STEP 6: CLI polls for token (should succeed now)
    print(f"\n[STEP 6] CLI polls for token...")
    token_response = await device_handler.poll_for_token(
        device_code=device_code,
        client_id="nubemsfc-cli"
    )

    assert "access_token" in token_response
    assert token_response["token_type"] == "Bearer"
    assert token_response["expires_in"] == 86400

    access_token = token_response["access_token"]
    print(f"  ✓ Token received: {access_token[:30]}...")

    # STEP 7: Verify token is valid JWT
    print(f"\n[STEP 7] Validating JWT token...")
    decoded = jwt.decode(
        access_token,
        device_handler.google_oauth.jwt_secret,
        algorithms=["HS256"],
        options={"verify_aud": False, "verify_exp": False}
    )

    assert decoded["email"] == user_info["email"]
    assert decoded["aud"] == "nubemsfc-cli-client"
    assert decoded["device_flow"] is True
    assert decoded["iss"] == "nubemsfc-mcp-server"

    print(f"  ✓ Token valid:")
    print(f"    - User: {decoded['email']}")
    print(f"    - Audience: {decoded['aud']}")
    print(f"    - Device flow: {decoded['device_flow']}")

    print(f"\n✅ COMPLETE DEVICE FLOW SUCCEEDED")


# ============================================================================
# SCENARIO 2: User Denies Authorization
# ============================================================================

@pytest.mark.asyncio
async def test_complete_device_flow_user_denies(device_handler):
    """
    Test complete device flow - user denies

    Flow:
    1. CLI requests device code
    2. User enters code in browser
    3. User denies authorization
    4. CLI polls and gets access_denied
    """

    print("\n[SCENARIO] User denies authorization...")

    # STEP 1: CLI requests device code
    device_code_response = await device_handler.generate_device_code(
        client_id="nubemsfc-cli",
        scope="openid email",
        client_ip="192.168.1.100"
    )

    device_code = device_code_response["device_code"]
    user_code = device_code_response["user_code"]

    print(f"  ✓ Device code generated")

    # STEP 2: User enters code
    verified = await device_handler.verify_user_code(user_code)
    assert verified is not None

    # STEP 3: User denies authorization
    print(f"  [User clicks 'Deny']")
    deny_success = await device_handler.deny_device(user_code)
    assert deny_success is True
    print(f"  ✓ Device denied")

    # STEP 4: CLI polls and gets access_denied
    token_response = await device_handler.poll_for_token(
        device_code=device_code,
        client_id="nubemsfc-cli"
    )

    assert token_response["error"] == "access_denied"
    print(f"  ✓ CLI receives access_denied")
    print(f"\n✅ DENIAL FLOW HANDLED CORRECTLY")


# ============================================================================
# SCENARIO 3: Device Code Expiration
# ============================================================================

@pytest.mark.asyncio
async def test_complete_device_flow_expiration(device_handler):
    """
    Test complete device flow - code expires

    Flow:
    1. CLI requests device code
    2. Time passes (code expires)
    3. User tries to enter expired code
    4. System rejects expired code
    """

    print("\n[SCENARIO] Device code expiration...")

    # STEP 1: CLI requests device code
    device_code_response = await device_handler.generate_device_code(
        client_id="nubemsfc-cli",
        scope="openid",
        client_ip="192.168.1.100"
    )

    device_code = device_code_response["device_code"]
    user_code = device_code_response["user_code"]

    print(f"  ✓ Device code generated")

    # STEP 2: Simulate expiration (delete from storage)
    print(f"  [15 minutes pass...]")
    await device_handler.storage.delete(device_code)
    print(f"  ✓ Device code expired")

    # STEP 3: User tries to verify expired code
    verified = await device_handler.verify_user_code(user_code)
    assert verified is None
    print(f"  ✓ Expired code rejected")

    # STEP 4: CLI polls and gets expired_token
    poll_response = await device_handler.poll_for_token(
        device_code=device_code,
        client_id="nubemsfc-cli"
    )

    assert poll_response["error"] == "expired_token"
    print(f"  ✓ CLI receives expired_token")
    print(f"\n✅ EXPIRATION HANDLED CORRECTLY")


# ============================================================================
# SCENARIO 4: Polling While Pending
# ============================================================================

@pytest.mark.asyncio
async def test_complete_device_flow_polling_pending(device_handler):
    """
    Test complete device flow - multiple polls while pending

    Flow:
    1. CLI requests device code
    2. CLI starts polling (before user approval)
    3. Each poll returns authorization_pending
    4. Respects 5-second interval
    """

    print("\n[SCENARIO] Polling while authorization pending...")

    # STEP 1: CLI requests device code
    device_code_response = await device_handler.generate_device_code(
        client_id="nubemsfc-cli",
        scope="openid",
        client_ip="192.168.1.100"
    )

    device_code = device_code_response["device_code"]
    print(f"  ✓ Device code generated")

    # STEP 2: First poll - should be authorization_pending
    print(f"\n  [CLI polls #1]")
    poll1 = await device_handler.poll_for_token(
        device_code=device_code,
        client_id="nubemsfc-cli"
    )
    assert poll1["error"] == "authorization_pending"
    print(f"  ✓ authorization_pending")

    # STEP 3: Immediate second poll - should be slow_down
    print(f"\n  [CLI polls #2 immediately]")
    poll2 = await device_handler.poll_for_token(
        device_code=device_code,
        client_id="nubemsfc-cli"
    )
    assert poll2["error"] == "slow_down"
    print(f"  ✓ slow_down (polling too fast)")

    # STEP 4: Wait and poll again
    print(f"\n  [Wait 5 seconds...]")
    await asyncio.sleep(5.1)

    print(f"  [CLI polls #3]")
    poll3 = await device_handler.poll_for_token(
        device_code=device_code,
        client_id="nubemsfc-cli"
    )
    assert poll3["error"] == "authorization_pending"
    print(f"  ✓ authorization_pending (allowed after wait)")

    print(f"\n✅ POLLING RATE LIMITING WORKS CORRECTLY")


# ============================================================================
# SCENARIO 5: Concurrent Polling from Multiple CLIs
# ============================================================================

@pytest.mark.asyncio
async def test_device_flow_single_use_token(device_handler):
    """
    Test device code is single-use

    Flow:
    1. CLI requests device code
    2. Device is approved
    3. CLI polls and gets token
    4. CLI tries to poll again - should fail (token already used)
    """

    print("\n[SCENARIO] Device code single-use enforcement...")

    # STEP 1: Generate and approve
    device_code_response = await device_handler.generate_device_code(
        client_id="nubemsfc-cli",
        scope="openid",
        client_ip="192.168.1.100"
    )

    device_code = device_code_response["device_code"]
    user_code = device_code_response["user_code"]

    user_info = {"email": "test@example.com", "google_id": "123"}
    await device_handler.approve_device(user_code, user_info)

    print(f"  ✓ Device code generated and approved")

    # STEP 2: First poll - gets token
    poll1 = await device_handler.poll_for_token(
        device_code=device_code,
        client_id="nubemsfc-cli"
    )

    assert "access_token" in poll1
    print(f"  ✓ Token received on first poll")

    # STEP 3: Second poll - should fail (single use)
    poll2 = await device_handler.poll_for_token(
        device_code=device_code,
        client_id="nubemsfc-cli"
    )

    assert poll2["error"] == "expired_token"
    print(f"  ✓ Second poll rejected (single-use enforced)")

    print(f"\n✅ SINGLE-USE ENFORCEMENT WORKS")


# ============================================================================
# SCENARIO 6: Client ID Mismatch
# ============================================================================

@pytest.mark.asyncio
async def test_device_flow_client_id_validation(device_handler):
    """
    Test client_id validation during polling

    Flow:
    1. CLI-A requests device code
    2. CLI-B tries to poll with different client_id
    3. System rejects due to client_id mismatch
    """

    print("\n[SCENARIO] Client ID validation...")

    # STEP 1: CLI-A requests device code
    device_code_response = await device_handler.generate_device_code(
        client_id="nubemsfc-cli-A",
        scope="openid",
        client_ip="192.168.1.100"
    )

    device_code = device_code_response["device_code"]
    print(f"  ✓ Device code generated for client: nubemsfc-cli-A")

    # STEP 2: CLI-B tries to poll with different client_id
    print(f"  [CLI-B tries to poll with wrong client_id]")
    poll_response = await device_handler.poll_for_token(
        device_code=device_code,
        client_id="nubemsfc-cli-B"  # Different client ID
    )

    assert poll_response["error"] == "invalid_client"
    print(f"  ✓ Poll rejected (client_id mismatch)")

    print(f"\n✅ CLIENT ID VALIDATION WORKS")


# ============================================================================
# SCENARIO 7: OAuth State Mapping
# ============================================================================

@pytest.mark.asyncio
async def test_oauth_state_to_device_mapping(device_handler):
    """
    Test OAuth state -> device_code mapping

    Flow:
    1. CLI requests device code
    2. User verifies code (initiates OAuth)
    3. OAuth state is stored -> device_code
    4. OAuth callback can find device_code by state
    """

    print("\n[SCENARIO] OAuth state mapping...")

    # STEP 1: Generate device code
    device_code_response = await device_handler.generate_device_code(
        client_id="nubemsfc-cli",
        scope="openid",
        client_ip="192.168.1.100"
    )

    device_code = device_code_response["device_code"]
    user_code = device_code_response["user_code"]

    print(f"  ✓ Device code generated")

    # STEP 2: Verify user code (would trigger OAuth redirect)
    verified = await device_handler.verify_user_code(user_code)
    assert verified == device_code

    # STEP 3: Store OAuth state (simulating what /auth/device/verify does)
    oauth_state = "test_oauth_state_abc123"
    await device_handler.storage.store_oauth_state(
        state=oauth_state,
        device_code=device_code,
        ttl=900
    )
    print(f"  ✓ OAuth state stored")

    # STEP 4: Retrieve device_code by OAuth state (simulating callback)
    retrieved_device_code = await device_handler.storage.get_by_oauth_state(oauth_state)
    assert retrieved_device_code == device_code
    print(f"  ✓ Device code retrieved by OAuth state")

    print(f"\n✅ OAUTH STATE MAPPING WORKS")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])  # -s to show print statements

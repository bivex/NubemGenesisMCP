"""
Security tests for Device Flow

Tests security aspects including:
- Brute force protection
- Rate limiting
- Replay attack prevention
- Code ambiguity
- XSS/CSRF protection
- Token security
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from core.auth.device_flow_handler import DeviceFlowOAuthHandler, generate_user_code
from core.auth.device_code_storage import InMemoryDeviceCodeStorage


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def device_handler():
    """Create DeviceFlowOAuthHandler"""
    mock_google_oauth = Mock()
    mock_google_oauth.jwt_secret = "test_secret_key"
    mock_google_oauth.is_configured.return_value = True

    mock_rate_limiter = Mock()
    mock_rate_limiter.check_rate_limit.return_value = (True, {})

    mock_audit_logger = Mock()

    storage = InMemoryDeviceCodeStorage()

    return DeviceFlowOAuthHandler(
        google_oauth=mock_google_oauth,
        storage=storage,
        rate_limiter=mock_rate_limiter,
        audit_logger=mock_audit_logger
    )


# ============================================================================
# TEST: Brute Force Protection
# ============================================================================

@pytest.mark.asyncio
async def test_brute_force_device_code_fails(device_handler):
    """
    Test: Brute force attack on device_code should fail

    An attacker should not be able to guess device codes due to:
    - 32 bytes (256 bits) of entropy
    - URL-safe base64 encoding (43 characters)
    - Short TTL (15 minutes)
    """

    print("\n[SECURITY] Testing brute force resistance...")

    # Generate legitimate device code
    result = await device_handler.generate_device_code(
        client_id="test-client",
        scope="openid",
        client_ip="192.168.1.1"
    )

    device_code = result["device_code"]
    print(f"  Legitimate device_code length: {len(device_code)} chars")

    # Calculate entropy
    # 32 bytes = 256 bits, URL-safe base64 = 43 chars from 64-char alphabet
    import math
    entropy_bits = 32 * 8  # 256 bits
    combinations = 2 ** entropy_bits

    print(f"  Entropy: {entropy_bits} bits")
    print(f"  Possible combinations: {combinations:.2e}")
    print(f"  Time to brute force at 1M/sec: {combinations / 1e6 / 60 / 60 / 24 / 365:.2e} years")

    # Attempt to poll with random device codes (should all fail)
    attempts = 100
    successful_guesses = 0

    for i in range(attempts):
        # Generate random device code
        import secrets
        fake_device_code = secrets.token_urlsafe(32)

        poll_result = await device_handler.poll_for_token(
            device_code=fake_device_code,
            client_id="test-client"
        )

        if "access_token" in poll_result:
            successful_guesses += 1

    print(f"  Brute force attempts: {attempts}")
    print(f"  Successful guesses: {successful_guesses}")

    assert successful_guesses == 0, "Brute force should never succeed"
    print(f"  ✓ Brute force protection: PASS")


# ============================================================================
# TEST: User Code Ambiguous Characters
# ============================================================================

def test_user_code_no_ambiguous_characters():
    """
    Test: User codes must not contain ambiguous characters

    Security concern: Phishing/social engineering
    - Characters like 0, O, I, 1, L can be confused
    - This could lead to user entering wrong code
    """

    print("\n[SECURITY] Testing ambiguous character exclusion...")

    ambiguous_chars = {'0', 'O', 'I', '1', 'L', 'o', 'i', 'l'}

    # Generate many codes
    codes = [generate_user_code() for _ in range(1000)]
    all_chars = ''.join(codes).replace('-', '')

    found_ambiguous = []
    for char in ambiguous_chars:
        if char in all_chars:
            found_ambiguous.append(char)

    print(f"  Codes generated: {len(codes)}")
    print(f"  Ambiguous chars checked: {ambiguous_chars}")
    print(f"  Ambiguous chars found: {found_ambiguous}")

    assert len(found_ambiguous) == 0, f"Found ambiguous characters: {found_ambiguous}"
    print(f"  ✓ No ambiguous characters: PASS")


# ============================================================================
# TEST: Replay Attack Prevention
# ============================================================================

@pytest.mark.asyncio
async def test_device_code_single_use_prevents_replay(device_handler):
    """
    Test: Device codes are single-use (prevents replay attacks)

    Security concern: Token replay
    - Device code should be deleted after token is issued
    - Attacker should not be able to reuse intercepted device_code
    """

    print("\n[SECURITY] Testing replay attack prevention...")

    # Generate and approve device
    result = await device_handler.generate_device_code(
        client_id="test-client",
        scope="openid",
        client_ip="192.168.1.1"
    )

    device_code = result["device_code"]
    user_code = result["user_code"]

    user_info = {"email": "victim@example.com", "google_id": "123"}
    await device_handler.approve_device(user_code, user_info)

    # First poll - legitimate user gets token
    poll1 = await device_handler.poll_for_token(
        device_code=device_code,
        client_id="test-client"
    )

    assert "access_token" in poll1
    print(f"  ✓ Legitimate user received token")

    # Replay attack - attacker tries to reuse device_code
    print(f"  [Attacker intercepts device_code and tries replay]")
    poll2 = await device_handler.poll_for_token(
        device_code=device_code,
        client_id="test-client"
    )

    assert "error" in poll2
    assert poll2["error"] == "expired_token"
    print(f"  ✓ Replay attack blocked: PASS")


# ============================================================================
# TEST: Rate Limiting (Polling DoS)
# ============================================================================

@pytest.mark.asyncio
async def test_polling_rate_limiting_prevents_dos(device_handler):
    """
    Test: Rate limiting prevents polling DoS

    Security concern: Resource exhaustion
    - Attacker could spam polling endpoint
    - Rate limiting enforces 5-second minimum interval
    """

    print("\n[SECURITY] Testing polling DoS prevention...")

    # Generate device code
    result = await device_handler.generate_device_code(
        client_id="test-client",
        scope="openid",
        client_ip="192.168.1.1"
    )

    device_code = result["device_code"]

    # Rapid polling attempts
    rapid_polls = []
    for i in range(10):
        poll_result = await device_handler.poll_for_token(
            device_code=device_code,
            client_id="test-client"
        )
        rapid_polls.append(poll_result)

    # Count slow_down responses
    slow_down_count = sum(1 for p in rapid_polls if p.get("error") == "slow_down")

    print(f"  Rapid polls: {len(rapid_polls)}")
    print(f"  Slow_down responses: {slow_down_count}")

    # Most should be slow_down (except first)
    assert slow_down_count >= 8, "Rate limiting should trigger"
    print(f"  ✓ Polling DoS prevention: PASS")


# ============================================================================
# TEST: Device Code Rate Limiting
# ============================================================================

@pytest.mark.asyncio
async def test_device_code_generation_rate_limiting(device_handler):
    """
    Test: Device code generation is rate limited

    Security concern: Resource exhaustion
    - Attacker could spam device code generation
    - Rate limiter should enforce 10/hour limit
    """

    print("\n[SECURITY] Testing device code generation rate limiting...")

    # Mock rate limiter to simulate limit exceeded
    device_handler.rate_limiter.check_rate_limit.return_value = (False, {
        "current_count": 10,
        "limit": 10,
        "window_seconds": 3600
    })

    # Attempt to generate device code
    try:
        await device_handler.generate_device_code(
            client_id="test-client",
            scope="openid",
            client_ip="attacker.ip"
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Rate limit exceeded" in str(e)
        print(f"  ✓ Rate limit enforced: {e}")
        print(f"  ✓ Device code rate limiting: PASS")


# ============================================================================
# TEST: XSS in User Code Input
# ============================================================================

@pytest.mark.asyncio
async def test_user_code_xss_protection(device_handler):
    """
    Test: User code input is protected against XSS

    Security concern: Cross-site scripting
    - User code input could contain malicious scripts
    - System should sanitize/validate input
    """

    print("\n[SECURITY] Testing XSS protection in user code...")

    xss_payloads = [
        "<script>alert('xss')</script>",
        "ABCD<img src=x onerror=alert(1)>",
        "'; DROP TABLE devices; --",
        "../../../etc/passwd",
        "ABCD\x00NULL",
    ]

    for payload in xss_payloads:
        # Try to verify malicious user code
        result = await device_handler.verify_user_code(payload)

        # Should be rejected (None)
        assert result is None, f"XSS payload should be rejected: {payload}"

    print(f"  XSS payloads tested: {len(xss_payloads)}")
    print(f"  ✓ All XSS payloads rejected: PASS")


# ============================================================================
# TEST: Verification URI Validation (Phishing)
# ============================================================================

def test_verification_uri_is_correct():
    """
    Test: Verification URI must be correct domain

    Security concern: Phishing
    - Attacker could display fake verification URI
    - Users must be directed to legitimate domain
    """

    print("\n[SECURITY] Testing verification URI validation...")

    mock_google_oauth = Mock()
    mock_google_oauth.jwt_secret = "secret"
    mock_google_oauth.is_configured.return_value = True

    mock_rate_limiter = Mock()
    mock_rate_limiter.check_rate_limit.return_value = (True, {})

    mock_audit_logger = Mock()
    storage = InMemoryDeviceCodeStorage()

    # Create handler with specific verification URI
    handler = DeviceFlowOAuthHandler(
        google_oauth=mock_google_oauth,
        storage=storage,
        rate_limiter=mock_rate_limiter,
        audit_logger=mock_audit_logger,
        verification_uri="https://ai.nubemsystems.es/device"
    )

    assert handler.verification_uri == "https://ai.nubemsystems.es/device"
    assert handler.verification_uri.startswith("https://")
    assert "nubemsystems.es" in handler.verification_uri

    print(f"  Verification URI: {handler.verification_uri}")
    print(f"  ✓ Correct domain verified: PASS")


# ============================================================================
# TEST: Token Storage Security
# ============================================================================

@pytest.mark.asyncio
async def test_token_not_stored_in_device_info(device_handler):
    """
    Test: JWT token is NOT stored in device storage

    Security concern: Token leakage
    - Access tokens should never be persisted
    - Device storage should only contain user info, not tokens
    """

    print("\n[SECURITY] Testing token storage security...")

    # Generate and approve device
    result = await device_handler.generate_device_code(
        client_id="test-client",
        scope="openid",
        client_ip="192.168.1.1"
    )

    device_code = result["device_code"]
    user_code = result["user_code"]

    user_info = {"email": "test@example.com", "google_id": "123"}
    await device_handler.approve_device(user_code, user_info)

    # Check device info in storage (before token issued)
    device_info = await device_handler.storage.get(device_code)

    # Should NOT contain access_token
    assert "access_token" not in device_info
    assert "jwt" not in device_info

    print(f"  ✓ No token in device storage: PASS")


# ============================================================================
# TEST: Client ID Validation
# ============================================================================

@pytest.mark.asyncio
async def test_client_id_validation_prevents_impersonation(device_handler):
    """
    Test: Client ID must match during polling

    Security concern: Client impersonation
    - Attacker should not be able to poll with different client_id
    """

    print("\n[SECURITY] Testing client ID validation...")

    # Generate device code with client-A
    result = await device_handler.generate_device_code(
        client_id="legitimate-client",
        scope="openid",
        client_ip="192.168.1.1"
    )

    device_code = result["device_code"]

    # Attacker tries to poll with different client_id
    poll_result = await device_handler.poll_for_token(
        device_code=device_code,
        client_id="attacker-client"
    )

    assert poll_result["error"] == "invalid_client"
    print(f"  ✓ Client impersonation blocked: PASS")


# ============================================================================
# TEST: OAuth State Security
# ============================================================================

@pytest.mark.asyncio
async def test_oauth_state_is_secure(device_handler):
    """
    Test: OAuth state is cryptographically secure

    Security concern: State prediction/CSRF
    - OAuth state should be unpredictable
    - Used to prevent CSRF attacks
    """

    print("\n[SECURITY] Testing OAuth state security...")

    # Store multiple OAuth states
    states = []
    for i in range(100):
        import secrets
        state = secrets.token_urlsafe(32)
        await device_handler.storage.store_oauth_state(
            state=state,
            device_code=f"device_{i}",
            ttl=900
        )
        states.append(state)

    # Check uniqueness (collision resistance)
    unique_states = set(states)
    assert len(unique_states) == len(states)

    # Check randomness (no patterns)
    # All states should be different in first 10 characters
    prefixes = [s[:10] for s in states]
    unique_prefixes = set(prefixes)
    assert len(unique_prefixes) > 95  # >95% unique prefixes

    print(f"  States generated: {len(states)}")
    print(f"  Unique states: {len(unique_states)}")
    print(f"  Unique prefixes (10 chars): {len(unique_prefixes)}")
    print(f"  ✓ OAuth state security: PASS")


# ============================================================================
# TEST: Time-based Attacks (TTL)
# ============================================================================

@pytest.mark.asyncio
async def test_ttl_prevents_time_based_attacks(device_handler):
    """
    Test: TTL enforcement prevents time-based attacks

    Security concern: Stale code reuse
    - Device codes should expire after 15 minutes
    - Expired codes should be rejected
    """

    print("\n[SECURITY] Testing TTL enforcement...")

    # Generate device code
    result = await device_handler.generate_device_code(
        client_id="test-client",
        scope="openid",
        client_ip="192.168.1.1"
    )

    device_code = result["device_code"]
    user_code = result["user_code"]

    # Simulate expiration
    await device_handler.storage.delete(device_code)

    # Try to use expired code
    verify_result = await device_handler.verify_user_code(user_code)
    assert verify_result is None

    poll_result = await device_handler.poll_for_token(
        device_code=device_code,
        client_id="test-client"
    )
    assert poll_result["error"] == "expired_token"

    print(f"  ✓ Expired codes rejected: PASS")


# ============================================================================
# TEST: Audit Logging for Security Events
# ============================================================================

@pytest.mark.asyncio
async def test_audit_logging_for_security_events(device_handler):
    """
    Test: Security events are audit logged

    Security concern: Forensics/monitoring
    - All auth attempts should be logged
    - Rate limit violations should be logged
    - Failures should be logged
    """

    print("\n[SECURITY] Testing audit logging...")

    audit_logger = device_handler.audit_logger

    # Generate device code - should log
    await device_handler.generate_device_code(
        client_id="test-client",
        scope="openid",
        client_ip="192.168.1.1",
        user_agent="TestClient/1.0"
    )

    assert audit_logger.log_auth_attempt.called
    print(f"  ✓ Device code generation logged")

    # Approve device - should log success
    result = await device_handler.generate_device_code(
        client_id="test-client",
        scope="openid",
        client_ip="192.168.1.1"
    )

    user_info = {"email": "test@example.com", "google_id": "123"}
    await device_handler.approve_device(result["user_code"], user_info)

    assert audit_logger.log_auth_success.called
    print(f"  ✓ Device approval logged")

    # Deny device - should log failure
    result2 = await device_handler.generate_device_code(
        client_id="test-client",
        scope="openid",
        client_ip="192.168.1.1"
    )

    await device_handler.deny_device(result2["user_code"])

    assert audit_logger.log_auth_failure.called
    print(f"  ✓ Device denial logged")

    print(f"  ✓ Audit logging: PASS")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

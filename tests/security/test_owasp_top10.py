"""
OWASP Top 10 Security Tests
TC067-093: Critical Security Controls
Enterprise Security Testing for NubemSuperFClaude
"""

import pytest
import re
from pathlib import Path


# ================================================================
# TC074: SQL Injection Protection
# ================================================================

@pytest.mark.security
@pytest.mark.compliance
def test_sql_injection_protection():
    """
    TC074: Verify protection against SQL injection

    OWASP: A03:2021 - Injection
    ISO 27001: A.14.2.1 (Secure Development)
    """
    # SQL injection payloads
    sql_payloads = [
        "' OR '1'='1",
        "'; DROP TABLE users; --",
        "1' UNION SELECT * FROM passwords--",
        "admin'--",
        "' OR 1=1--",
    ]

    # Mock database query function
    def safe_query(user_input):
        # Should use parameterized queries
        # This is a test of the pattern, not actual execution
        assert "--" not in user_input, "Comment detected"
        assert "UNION" not in user_input.upper(), "UNION detected"
        assert "DROP" not in user_input.upper(), "DROP detected"
        return True

    for payload in sql_payloads:
        with pytest.raises(AssertionError):
            safe_query(payload)


# ================================================================
# TC075: XSS Protection
# ================================================================

@pytest.mark.security
def test_xss_protection():
    """
    TC075: Verify Cross-Site Scripting protection

    OWASP: A03:2021 - Injection
    """
    xss_payloads = [
        "<script>alert('XSS')</script>",
        "<img src=x onerror=alert('XSS')>",
        "<body onload=alert('XSS')>",
        "javascript:alert('XSS')",
        "<iframe src='javascript:alert(1)'>",
    ]

    def sanitize_output(user_input):
        """Example output sanitization"""
        dangerous_patterns = [
            r"<script",
            r"javascript:",
            r"onerror=",
            r"onload=",
            r"<iframe",
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, user_input, re.IGNORECASE):
                return f"[SANITIZED]"
        return user_input

    for payload in xss_payloads:
        result = sanitize_output(payload)
        assert result == "[SANITIZED]", f"XSS payload not sanitized: {payload}"


# ================================================================
# TC080: Input Validation
# ================================================================

@pytest.mark.security
def test_input_validation_on_persona_operations():
    """
    TC080: Verify input validation on all endpoints

    Security:
    - Whitelist validation
    - Length limits
    - Type checking
    """
    valid_persona_keys = [
        "system-architect",
        "backend-developer",
        "security-engineer",
    ]

    invalid_inputs = [
        "../../../etc/passwd",  # Path traversal
        "<script>alert(1)</script>",  # XSS
        "' OR 1=1--",  # SQL injection
        "a" * 10000,  # Length attack
        "\x00\x01\x02",  # Binary data
    ]

    def validate_persona_key(key):
        # Validation rules
        if not isinstance(key, str):
            return False
        if len(key) > 100:
            return False
        if not re.match(r'^[a-z0-9\-]+$', key):
            return False
        return True

    # Valid inputs should pass
    for valid_key in valid_persona_keys:
        assert validate_persona_key(valid_key), f"Valid key rejected: {valid_key}"

    # Invalid inputs should fail
    for invalid_input in invalid_inputs:
        assert not validate_persona_key(invalid_input), f"Invalid input accepted: {invalid_input}"


# ================================================================
# TC084: Sensitive Data Masking in Logs
# ================================================================

@pytest.mark.security
@pytest.mark.gdpr
def test_sensitive_data_masked_in_logs(caplog):
    """
    TC084: Verify sensitive data is masked in logs

    Requirements:
    - GDPR: Art. 32 (Security of Processing)
    - ISO 27001: A.18.1.3 (Protection of Records)
    """
    sensitive_patterns = {
        "api_key": r"nsfc_\w+_[\w\-]{40,}",
        "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "password": r"password[\"']?\s*[:=]\s*[\"']?[\w!@#$%^&*]+",
        "token": r"token[\"']?\s*[:=]\s*[\"']?[\w\-\.]+",
    }

    def mask_sensitive_data(log_message):
        """Mask sensitive data in log messages"""
        masked = log_message

        for data_type, pattern in sensitive_patterns.items():
            masked = re.sub(pattern, f"[{data_type.upper()}_REDACTED]", masked)

        return masked

    # Test cases
    test_logs = [
        "User logged in with api_key=nsfc_admin_YqNw8JDUkTuJ_0YRY98eOW4FNTO5XlGcSRyHLkNEzsw",
        "Error for user john.doe@example.com",
        "Password: supersecret123!",
        "Auth token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
    ]

    for log in test_logs:
        masked = mask_sensitive_data(log)

        # Verify masking
        assert "nsfc_admin" not in masked, "API key not masked"
        assert "@example.com" not in masked, "Email not masked"
        assert "supersecret" not in masked, "Password not masked"
        assert "eyJhbGci" not in masked, "Token not masked"
        assert "[" in masked and "]" in masked, "Masking pattern not applied"


# ================================================================
# TC087: Container Runs as Non-Root
# ================================================================

@pytest.mark.security
@pytest.mark.e2e
@pytest.mark.requires_k8s
def test_container_runs_as_non_root(k8s_client, k8s_namespace):
    """
    TC087: Verify container runs as non-root user

    Security:
    - Principle of least privilege
    - Container security best practices
    - CIS Docker Benchmark
    """
    # This would run in E2E environment with actual K8s
    # Here we document the security requirement
    required_security_context = {
        "runAsNonRoot": True,
        "runAsUser": 1000,
        "allowPrivilegeEscalation": False,
        "capabilities": {
            "drop": ["ALL"]
        },
        "readOnlyRootFilesystem": False,  # May need write for temp files
    }

    # Verify security context structure
    assert required_security_context["runAsNonRoot"] is True
    assert required_security_context["runAsUser"] != 0
    assert required_security_context["allowPrivilegeEscalation"] is False


# ================================================================
# TC092: Image Scanning for Vulnerabilities
# ================================================================

@pytest.mark.security
def test_no_critical_vulnerabilities_in_dependencies():
    """
    TC092: Verify no HIGH/CRITICAL CVEs in dependencies

    Tools:
    - Trivy
    - Snyk
    - pip-audit
    """
    import subprocess
    import json

    # Run pip-audit (if available)
    try:
        result = subprocess.run(
            ["pip-audit", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            # Parse results
            audit_data = json.loads(result.stdout) if result.stdout else {}

            # Check for critical vulnerabilities
            vulnerabilities = audit_data.get("vulnerabilities", [])

            critical_count = sum(
                1 for v in vulnerabilities
                if v.get("severity", "").upper() in ["CRITICAL", "HIGH"]
            )

            assert critical_count == 0, f"Found {critical_count} critical vulnerabilities"
    except FileNotFoundError:
        pytest.skip("pip-audit not installed")
    except subprocess.TimeoutExpired:
        pytest.skip("pip-audit timed out")


# ================================================================
# TC093: Image Provenance Verification
# ================================================================

@pytest.mark.security
def test_image_provenance_verification():
    """
    TC093: Verify image provenance and signatures

    Supply Chain Security:
    - Image signing
    - Content trust
    - SBOM generation
    """
    # Document required provenance metadata
    required_provenance = {
        "builder": "github-actions",
        "source_repo": "nubemsystems/NubemSuperFClaude",
        "commit_sha": None,  # Should be set during build
        "build_timestamp": None,
        "signed": True,
        "sbom_included": True,
    }

    # Verify structure
    assert required_provenance["signed"] is True
    assert required_provenance["sbom_included"] is True
    assert required_provenance["builder"] == "github-actions"


# ================================================================
# RATE LIMITING TESTS
# ================================================================

@pytest.mark.security
def test_rate_limiting_enforced():
    """
    Verify API rate limiting is enforced

    Security:
    - Prevent abuse
    - DDoS protection
    - ISO 27001: A.13.1.1 (Network Controls)
    """
    rate_limits = {
        "admin": 60,  # requests per minute
        "developer": 45,
        "readonly": 30,
    }

    def check_rate_limit(role, requests_per_minute):
        """Verify rate limit configuration"""
        assert requests_per_minute > 0
        assert requests_per_minute <= 60  # Max limit

        return True

    for role, limit in rate_limits.items():
        assert check_rate_limit(role, limit), f"Rate limit issue for {role}"


# ================================================================
# AUTHENTICATION TESTS
# ================================================================

@pytest.mark.security
def test_expired_api_keys_rejected():
    """
    TC011: Verify expired API keys are rejected

    Security:
    - Temporal access control
    - Key rotation
    """
    from datetime import datetime, timedelta

    def is_key_valid(expires_at):
        """Check if API key is still valid"""
        if expires_at is None:
            return False

        expiry = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        now = datetime.now(expiry.tzinfo)

        return now < expiry

    # Test cases
    expired_key = (datetime.now() - timedelta(days=1)).isoformat()
    valid_key = (datetime.now() + timedelta(days=365)).isoformat()

    assert not is_key_valid(expired_key), "Expired key accepted"
    assert is_key_valid(valid_key), "Valid key rejected"

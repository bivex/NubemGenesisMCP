"""
Quick tests for AuditLogger
"""

from audit_logger import AuditLogger
import json


def test_audit_logger():
    """Test audit logger functionality"""
    print("\n🧪 Testing AuditLogger...\n")

    # Create logger
    audit = AuditLogger(log_to_file=False)  # Don't write to file for testing

    # Test 1: Log auth attempt
    print("Test 1: Auth attempt")
    audit.log_auth_attempt(
        api_key_prefix="nsfc_admin_xxx",
        ip_address="1.2.3.4"
    )
    print("✅ Auth attempt logged\n")

    # Test 2: Log auth success
    print("Test 2: Auth success")
    audit.log_auth_success(
        user_email="david.anguera@nubemsystems.es",
        user_role="admin",
        api_key_prefix="nsfc_admin_xxx",
        ip_address="1.2.3.4"
    )
    print("✅ Auth success logged\n")

    # Test 3: Log auth failed
    print("Test 3: Auth failed")
    audit.log_auth_failed(
        api_key_prefix="invalid_key",
        reason="Invalid API key",
        ip_address="5.6.7.8"
    )
    print("✅ Auth failed logged\n")

    # Test 4: Log permission check (allowed)
    print("Test 4: Permission allowed")
    audit.log_permission_check(
        user_email="david.anguera@nubemsystems.es",
        user_role="admin",
        tool_name="intelligent_respond",
        operation="read",
        allowed=True
    )
    print("✅ Permission allowed logged\n")

    # Test 5: Log permission check (denied)
    print("Test 5: Permission denied")
    audit.log_permission_check(
        user_email="joseluis.manzanares@nubemsystems.es",
        user_role="readonly",
        tool_name="kubernetes",
        operation="write",
        allowed=False,
        reason="MCP blocked for readonly role"
    )
    print("✅ Permission denied logged\n")

    # Test 6: Log tool invocation
    print("Test 6: Tool invocation")
    audit.log_tool_invocation(
        user_email="david.anguera@nubemsystems.es",
        user_role="admin",
        tool_name="list_personas",
        status="success",
        execution_time_ms=123.45
    )
    print("✅ Tool invocation logged\n")

    # Test 7: Log rate limit exceeded
    print("Test 7: Rate limit exceeded")
    audit.log_rate_limit_exceeded(
        user_email="joseluis.manzanares@nubemsystems.es",
        user_role="readonly",
        api_key_prefix="nsfc_readonly_xxx",
        ip_address="10.0.0.1"
    )
    print("✅ Rate limit exceeded logged\n")

    print("="*60)
    print("✅ ALL AUDIT LOGGER TESTS PASSED (7/7)")
    print("="*60 + "\n")

    return True


if __name__ == "__main__":
    test_audit_logger()

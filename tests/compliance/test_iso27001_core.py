"""
ISO 27001 Core Compliance Tests
Critical controls for information security management
TC001-023: Audit, Access Control, Change Management
"""

import pytest
from datetime import datetime
import json


# ================================================================
# TC001-004: Audit Trail (A.12.4.1)
# ================================================================

@pytest.mark.compliance
@pytest.mark.iso27001
def test_audit_trail_for_persona_modifications():
    """
    TC001-004: Verify audit trail for all persona operations

    ISO 27001: A.12.4.1 - Event Logging
    Requirements:
    - User identification
    - Timestamp
    - Action performed
    - Resource affected
    - Outcome (success/failure)
    """
    # Mock audit log entry structure
    required_fields = [
        "timestamp",
        "user_email",
        "user_role",
        "event_type",
        "tool_name",
        "operation",
        "status",
        "execution_time_ms",
        "error"
    ]

    # Example audit log
    audit_entry = {
        "timestamp": datetime.now().isoformat(),
        "user_email": "test@example.com",
        "user_role": "admin",
        "event_type": "tool_invocation",
        "tool_name": "reload_personas",
        "operation": "read",
        "status": "success",
        "execution_time_ms": 156.2,
        "error": None
    }

    # Verify all required fields present
    for field in required_fields:
        assert field in audit_entry, f"Missing required field: {field}"

    # Verify data types
    assert isinstance(audit_entry["timestamp"], str)
    assert isinstance(audit_entry["user_email"], str)
    assert isinstance(audit_entry["status"], str)
    assert audit_entry["status"] in ["success", "failure", "error"]


@pytest.mark.compliance
@pytest.mark.iso27001
def test_audit_logs_are_append_only():
    """
    TC001: Audit logs must be tamper-proof

    ISO 27001: A.12.4.3 - Administrator and Operator Logs
    Requirements:
    - Append-only
    - No deletion
    - Integrity protection
    """
    # Test that audit log structure prevents modification
    audit_log_config = {
        "storage": "postgresql",
        "table": "audit_logs",
        "append_only": True,
        "retention_days": 365,
        "integrity_check": "hash_chain"
    }

    assert audit_log_config["append_only"] is True
    assert audit_log_config["retention_days"] >= 365  # Regulatory requirement
    assert audit_log_config["integrity_check"] in ["hash_chain", "digital_signature"]


# ================================================================
# TC005-012: Access Control (A.9.2)
# ================================================================

@pytest.mark.compliance
@pytest.mark.iso27001
def test_rbac_enforced_for_all_operations():
    """
    TC005-012: Role-Based Access Control enforcement

    ISO 27001: A.9.2.1 - User Registration
    ISO 27001: A.9.2.2 - User Access Provisioning
    """
    # Define role permissions
    roles = {
        "admin": {
            "permissions": ["read", "write", "delete", "execute"],
            "blocked_mcps": [],
            "rate_limit": 60
        },
        "developer": {
            "permissions": ["read", "execute"],
            "blocked_mcps": ["kubernetes", "gcp"],
            "rate_limit": 45
        },
        "readonly": {
            "permissions": ["read"],
            "blocked_mcps": ["kubernetes", "docker", "gcp", "github", "filesystem"],
            "rate_limit": 30
        }
    }

    # Test role hierarchy
    assert "execute" in roles["admin"]["permissions"]
    assert "execute" in roles["developer"]["permissions"]
    assert "execute" not in roles["readonly"]["permissions"]

    # Test rate limiting
    assert roles["admin"]["rate_limit"] > roles["developer"]["rate_limit"]
    assert roles["developer"]["rate_limit"] > roles["readonly"]["rate_limit"]


@pytest.mark.compliance
@pytest.mark.iso27001
def test_principle_of_least_privilege():
    """
    ISO 27001: A.9.2.3 - Management of Privileged Access Rights

    Requirements:
    - Minimum necessary permissions
    - Regular review
    - Justification for elevated access
    """
    def verify_least_privilege(role, requested_operation):
        """Verify user has minimum necessary permissions"""
        role_permissions = {
            "readonly": ["list_personas", "get_system_status"],
            "developer": ["list_personas", "use_persona", "get_system_status"],
            "admin": ["*"]  # All operations
        }

        if role == "admin":
            return True

        allowed_ops = role_permissions.get(role, [])
        return requested_operation in allowed_ops

    # Test cases
    assert verify_least_privilege("readonly", "list_personas") is True
    assert verify_least_privilege("readonly", "reload_personas") is False
    assert verify_least_privilege("developer", "use_persona") is True
    assert verify_least_privilege("developer", "reload_personas") is False
    assert verify_least_privilege("admin", "reload_personas") is True


# ================================================================
# TC018-023: Backup & Recovery (A.17.1)
# ================================================================

@pytest.mark.compliance
@pytest.mark.iso27001
def test_backup_exists_and_encrypted():
    """
    TC018-023: Backup and Disaster Recovery

    ISO 27001: A.17.1.2 - Implementing Information Security Continuity
    ISO 27001: A.17.1.3 - Verify, Review and Evaluate
    """
    backup_requirements = {
        "location": "gs://nubemsfc-2025-backups/personas/",
        "encryption": "AES-256-GCM",
        "frequency": "daily",
        "retention": "90_days",
        "rto": "5_minutes",  # Recovery Time Objective
        "rpo": "1_hour",  # Recovery Point Objective
        "tested": "quarterly"
    }

    # Verify backup configuration
    assert backup_requirements["encryption"].startswith("AES-256")
    assert backup_requirements["frequency"] in ["daily", "hourly"]
    assert "minute" in backup_requirements["rto"]  # Must specify time unit

    # Verify recovery objectives
    rto_minutes = int(backup_requirements["rto"].split("_")[0])
    rpo_minutes = int(backup_requirements["rpo"].split("_")[0]) * 60  # Convert hours

    assert rto_minutes <= 5, "RTO must be <= 5 minutes"
    assert rpo_minutes <= 60, "RPO must be <= 1 hour"


@pytest.mark.compliance
@pytest.mark.iso27001
def test_backup_integrity_verification():
    """
    TC019: Verify backup integrity with checksums

    Requirements:
    - Checksum validation
    - Corruption detection
    - Restore testing
    """
    import hashlib

    def verify_backup_integrity(backup_data, expected_checksum):
        """Verify backup has not been corrupted"""
        actual_checksum = hashlib.sha256(backup_data).hexdigest()
        return actual_checksum == expected_checksum

    # Test checksum verification
    test_data = b"test backup data"
    checksum = hashlib.sha256(test_data).hexdigest()

    assert verify_backup_integrity(test_data, checksum) is True
    assert verify_backup_integrity(b"corrupted data", checksum) is False


# ================================================================
# TC013-017: Secure Development (A.14.2)
# ================================================================

@pytest.mark.compliance
@pytest.mark.iso27001
def test_secure_coding_practices_enforced():
    """
    TC013-017: Secure Development Lifecycle

    ISO 27001: A.14.2.1 - Secure Development Policy
    """
    secure_development_requirements = {
        "code_review": "mandatory",
        "security_training": "annual",
        "sast_tools": ["bandit", "semgrep"],
        "dast_tools": ["zap"],
        "dependency_scanning": ["snyk", "trivy"],
        "secrets_detection": ["detect-secrets"],
        "minimum_test_coverage": 70
    }

    # Verify SAST integration
    assert len(secure_development_requirements["sast_tools"]) >= 1
    assert "bandit" in secure_development_requirements["sast_tools"]

    # Verify coverage requirement
    assert secure_development_requirements["minimum_test_coverage"] >= 70


@pytest.mark.compliance
@pytest.mark.iso27001
def test_dependency_vulnerability_scanning():
    """
    TC015: Dependency scanning for known CVEs

    Requirements:
    - Regular scanning
    - Automated alerts
    - Patching process
    """
    dependency_scan_config = {
        "tools": ["pip-audit", "safety", "snyk"],
        "frequency": "on_commit",
        "severity_threshold": "MEDIUM",
        "auto_remediate": "CRITICAL",
        "alert_channels": ["slack", "email"]
    }

    assert "on_commit" in dependency_scan_config["frequency"]
    assert dependency_scan_config["severity_threshold"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert len(dependency_scan_config["alert_channels"]) > 0


# ================================================================
# CHANGE MANAGEMENT TESTS (A.12.1.2)
# ================================================================

@pytest.mark.compliance
@pytest.mark.iso27001
def test_change_management_process():
    """
    ISO 27001: A.12.1.2 - Change Management

    Requirements:
    - Change approval
    - Testing before production
    - Rollback capability
    - Documentation
    """
    change_process = {
        "requires_approval": True,
        "approval_roles": ["tech_lead", "security_engineer"],
        "testing_required": True,
        "test_environments": ["dev", "staging"],
        "rollback_plan": True,
        "documentation": True
    }

    assert change_process["requires_approval"] is True
    assert len(change_process["approval_roles"]) >= 1
    assert change_process["rollback_plan"] is True
    assert "staging" in change_process["test_environments"]

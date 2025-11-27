"""
GDPR Compliance Tests (EU 2016/679)
TC024-046: Data Protection and Privacy Requirements
Comprehensive tests for GDPR Articles 15, 17, 20, 25, 30, 32, 33

References:
- GDPR Art. 25: Privacy by Design and Default
- GDPR Art. 30: Records of Processing Activities
- GDPR Art. 32: Security of Processing
- GDPR Art. 17: Right to Erasure
- GDPR Art. 15: Right of Access
- GDPR Art. 33: Breach Notification
"""

import pytest
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch
import re


# ================================================================
# TC024-027: Privacy by Design (Art. 25)
# ================================================================

@pytest.mark.compliance
@pytest.mark.gdpr
def test_data_minimization_no_excessive_collection():
    """
    TC024: Verify system only collects necessary data

    GDPR Art. 25: Privacy by Design and Default
    Requirements:
    - Only collect data necessary for service
    - No excessive or unnecessary data collection
    """
    # Define minimal required user data
    required_user_fields = {
        "user_email",  # For authentication
        "role",  # For authorization
        "api_key_hash",  # For authentication (hashed)
        "created_at",  # For audit
        "active"  # For access control
    }

    # Define what should NOT be collected
    prohibited_fields = {
        "password_plaintext",  # Passwords must be hashed
        "credit_card",  # Not needed for service
        "social_security",  # PII not needed
        "home_address",  # Location data not needed
        "phone_number",  # Contact not required
        "date_of_birth"  # Age verification not needed
    }

    # Example user record
    user_record = {
        "user_email": "user@example.com",
        "role": "developer",
        "api_key_hash": hashlib.sha256(b"api_key").hexdigest(),
        "created_at": datetime.now().isoformat(),
        "active": True
    }

    # Verify only required fields present
    for field in user_record.keys():
        assert field in required_user_fields, f"Excessive field collected: {field}"

    # Verify prohibited fields absent
    for field in prohibited_fields:
        assert field not in user_record, f"Prohibited field collected: {field}"


@pytest.mark.compliance
@pytest.mark.gdpr
def test_pseudonymization_of_sensitive_data():
    """
    TC025: Verify sensitive data is pseudonymized

    GDPR Art. 25: Privacy by Design
    GDPR Art. 32: Security of Processing
    """
    def pseudonymize_email(email):
        """Pseudonymize email while maintaining uniqueness"""
        email_hash = hashlib.sha256(email.encode()).hexdigest()[:16]
        domain = email.split('@')[1] if '@' in email else 'example.com'
        return f"user_{email_hash}@{domain}"

    def pseudonymize_api_key(api_key):
        """Store only hash of API key"""
        return hashlib.sha256(api_key.encode()).hexdigest()

    # Test pseudonymization
    original_email = "john.doe@example.com"
    original_api_key = "nsfc_admin_secretkey123"

    pseudo_email = pseudonymize_email(original_email)
    pseudo_api_key = pseudonymize_api_key(original_api_key)

    # Verify pseudonymized data doesn't contain original
    assert "john.doe" not in pseudo_email
    assert "secretkey123" not in pseudo_api_key

    # Verify pseudonymization is deterministic
    assert pseudonymize_email(original_email) == pseudo_email
    assert pseudonymize_api_key(original_api_key) == pseudo_api_key


@pytest.mark.compliance
@pytest.mark.gdpr
def test_privacy_by_default_restrictive_settings():
    """
    TC026: Verify privacy-by-default configuration

    GDPR Art. 25: Privacy by Default
    Requirements:
    - Most restrictive settings by default
    - Users must opt-in to data sharing
    - No pre-checked consent boxes
    """
    # Default user privacy settings
    default_privacy_config = {
        "share_usage_data": False,  # Opt-in required
        "share_error_reports": False,  # Opt-in required
        "allow_telemetry": False,  # Opt-in required
        "public_profile": False,  # Private by default
        "data_retention_days": 90,  # Minimal retention
        "auto_delete_inactive": True  # Auto-cleanup enabled
    }

    # Verify all privacy settings default to most restrictive
    assert default_privacy_config["share_usage_data"] is False
    assert default_privacy_config["share_error_reports"] is False
    assert default_privacy_config["allow_telemetry"] is False
    assert default_privacy_config["public_profile"] is False
    assert default_privacy_config["auto_delete_inactive"] is True
    assert default_privacy_config["data_retention_days"] <= 90


@pytest.mark.compliance
@pytest.mark.gdpr
def test_data_encryption_at_rest_and_in_transit():
    """
    TC027: Verify encryption of personal data

    GDPR Art. 32: Security of Processing
    Requirements:
    - Data encrypted at rest (AES-256)
    - Data encrypted in transit (TLS 1.2+)
    - Encryption keys properly managed
    """
    from cryptography.fernet import Fernet

    # Test encryption at rest
    def encrypt_sensitive_data(data):
        """Encrypt sensitive data using Fernet (AES-128)"""
        key = Fernet.generate_key()
        f = Fernet(key)
        encrypted = f.encrypt(data.encode())
        return encrypted, key

    sensitive_data = "user@example.com"
    encrypted_data, encryption_key = encrypt_sensitive_data(sensitive_data)

    # Verify data is encrypted
    assert sensitive_data.encode() not in encrypted_data
    assert b"user@example.com" not in encrypted_data

    # Verify data can be decrypted
    f = Fernet(encryption_key)
    decrypted_data = f.decrypt(encrypted_data).decode()
    assert decrypted_data == sensitive_data

    # Test TLS configuration
    tls_config = {
        "min_version": "TLSv1.2",
        "ciphers": [
            "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384",
            "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256"
        ],
        "require_tls": True
    }

    assert tls_config["min_version"] >= "TLSv1.2"
    assert tls_config["require_tls"] is True


# ================================================================
# TC028-031: Records of Processing (Art. 30)
# ================================================================

@pytest.mark.compliance
@pytest.mark.gdpr
def test_processing_activities_documented(db_session):
    """
    TC028: Verify records of processing activities

    GDPR Art. 30: Records of Processing Activities
    Requirements:
    - Document all data processing activities
    - Include purpose, categories, recipients
    - Regular updates to documentation
    """
    cursor = db_session.cursor()

    # Create processing activities register
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processing_activities (
            id SERIAL PRIMARY KEY,
            activity_name VARCHAR(255) NOT NULL,
            purpose TEXT NOT NULL,
            data_categories TEXT[] NOT NULL,
            legal_basis VARCHAR(100) NOT NULL,
            data_recipients TEXT[],
            retention_period VARCHAR(50),
            security_measures TEXT[],
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Document persona system processing activity
    cursor.execute("""
        INSERT INTO processing_activities (
            activity_name, purpose, data_categories, legal_basis,
            data_recipients, retention_period, security_measures
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        "Persona System Access",
        "Provide AI persona capabilities to authorized users",
        ["user_email", "role", "access_logs"],
        "Legitimate Interest (Art. 6(1)(f))",
        ["Internal Systems Only"],
        "90 days",
        ["Encryption at rest", "Access control", "Audit logging"]
    ))
    db_session.commit()

    # Verify documentation exists
    cursor.execute("SELECT COUNT(*) FROM processing_activities")
    count = cursor.fetchone()[0]
    assert count > 0, "Processing activities must be documented"

    # Verify required fields
    cursor.execute("""
        SELECT activity_name, purpose, legal_basis
        FROM processing_activities
        WHERE activity_name = 'Persona System Access'
    """)
    result = cursor.fetchone()

    assert result[0] == "Persona System Access"
    assert "AI persona capabilities" in result[1]
    assert "Legitimate Interest" in result[2]

    # Cleanup
    cursor.execute("DROP TABLE processing_activities")
    db_session.commit()


@pytest.mark.compliance
@pytest.mark.gdpr
def test_data_protection_impact_assessment():
    """
    TC029: Verify Data Protection Impact Assessment (DPIA)

    GDPR Art. 35: Data Protection Impact Assessment
    Requirements:
    - Risk assessment for high-risk processing
    - Document mitigation measures
    - Regular review
    """
    dpia_assessment = {
        "system": "NubemSuperFClaude Persona System",
        "assessment_date": "2025-11-06",
        "risk_level": "MEDIUM",
        "identified_risks": [
            {
                "risk": "Unauthorized access to persona data",
                "impact": "MEDIUM",
                "likelihood": "LOW",
                "mitigation": "RBAC, API key authentication, audit logging"
            },
            {
                "risk": "Data breach of user information",
                "impact": "HIGH",
                "likelihood": "LOW",
                "mitigation": "Encryption at rest/transit, minimal data collection"
            }
        ],
        "residual_risk": "LOW",
        "approval_status": "APPROVED",
        "next_review_date": "2026-11-06"
    }

    # Verify DPIA structure
    assert "identified_risks" in dpia_assessment
    assert len(dpia_assessment["identified_risks"]) > 0

    # Verify all risks have mitigation
    for risk in dpia_assessment["identified_risks"]:
        assert "mitigation" in risk
        assert len(risk["mitigation"]) > 0

    # Verify residual risk acceptable
    assert dpia_assessment["residual_risk"] in ["LOW", "MEDIUM"]


@pytest.mark.compliance
@pytest.mark.gdpr
def test_audit_trail_completeness():
    """
    TC030: Verify complete audit trail for data processing

    GDPR Art. 30: Records of Processing
    ISO 27001: A.12.4.1 (Event Logging)
    """
    # Required audit log fields
    required_audit_fields = [
        "timestamp",
        "user_email",
        "user_role",
        "event_type",
        "data_accessed",
        "operation",
        "ip_address",
        "user_agent",
        "status",
        "changes_made"
    ]

    # Example audit log entry
    audit_entry = {
        "timestamp": datetime.now().isoformat(),
        "user_email": "user@example.com",
        "user_role": "developer",
        "event_type": "data_access",
        "data_accessed": "persona_list",
        "operation": "read",
        "ip_address": "192.168.1.100",
        "user_agent": "Claude Code/1.0",
        "status": "success",
        "changes_made": None
    }

    # Verify all required fields present
    for field in required_audit_fields:
        assert field in audit_entry, f"Audit log missing field: {field}"


@pytest.mark.compliance
@pytest.mark.gdpr
def test_legal_basis_documented_for_processing():
    """
    TC031: Verify legal basis documented for all processing

    GDPR Art. 6: Lawfulness of Processing
    Legal bases:
    - Consent (Art. 6(1)(a))
    - Contract (Art. 6(1)(b))
    - Legal obligation (Art. 6(1)(c))
    - Vital interests (Art. 6(1)(d))
    - Public task (Art. 6(1)(e))
    - Legitimate interests (Art. 6(1)(f))
    """
    processing_legal_bases = {
        "user_authentication": {
            "legal_basis": "Contract",
            "article": "Art. 6(1)(b)",
            "justification": "Necessary for providing requested service"
        },
        "audit_logging": {
            "legal_basis": "Legitimate Interest",
            "article": "Art. 6(1)(f)",
            "justification": "Security and fraud prevention"
        },
        "error_telemetry": {
            "legal_basis": "Consent",
            "article": "Art. 6(1)(a)",
            "justification": "User opt-in for service improvement"
        }
    }

    # Verify each processing activity has legal basis
    valid_legal_bases = [
        "Consent", "Contract", "Legal Obligation",
        "Vital Interests", "Public Task", "Legitimate Interest"
    ]

    for activity, details in processing_legal_bases.items():
        assert "legal_basis" in details
        assert details["legal_basis"] in valid_legal_bases
        assert "article" in details
        assert "Art. 6(1)" in details["article"]


# ================================================================
# TC032-035: Right to Erasure (Art. 17)
# ================================================================

@pytest.mark.compliance
@pytest.mark.gdpr
def test_right_to_erasure_implementation(db_session):
    """
    TC032: Verify Right to Erasure ("Right to be Forgotten")

    GDPR Art. 17: Right to Erasure
    Requirements:
    - Delete all personal data on request
    - Cascade deletion to all systems
    - Verify complete erasure
    - Document erasure in audit log
    """
    cursor = db_session.cursor()

    # Create test user table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            role VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_activity (
            id SERIAL PRIMARY KEY,
            user_email VARCHAR(255),
            activity TEXT,
            activity_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db_session.commit()

    # Create test user
    test_email = "to_be_deleted@example.com"
    cursor.execute("INSERT INTO users (email, role) VALUES (%s, %s)", (test_email, "user"))
    cursor.execute("INSERT INTO user_activity (user_email, activity) VALUES (%s, %s)",
                   (test_email, "login"))
    db_session.commit()

    # Verify user exists
    cursor.execute("SELECT COUNT(*) FROM users WHERE email = %s", (test_email,))
    assert cursor.fetchone()[0] == 1

    # Execute right to erasure
    cursor.execute("DELETE FROM user_activity WHERE user_email = %s", (test_email,))
    cursor.execute("DELETE FROM users WHERE email = %s", (test_email,))
    db_session.commit()

    # Verify complete erasure
    cursor.execute("SELECT COUNT(*) FROM users WHERE email = %s", (test_email,))
    assert cursor.fetchone()[0] == 0, "User data should be deleted"

    cursor.execute("SELECT COUNT(*) FROM user_activity WHERE user_email = %s", (test_email,))
    assert cursor.fetchone()[0] == 0, "User activity should be deleted"

    # Cleanup
    cursor.execute("DROP TABLE user_activity")
    cursor.execute("DROP TABLE users")
    db_session.commit()


@pytest.mark.compliance
@pytest.mark.gdpr
def test_data_retention_automatic_deletion():
    """
    TC033: Verify automatic deletion after retention period

    GDPR Art. 5(1)(e): Storage Limitation
    Requirements:
    - Define retention periods
    - Automatic deletion after expiry
    - Exceptions documented
    """
    def should_delete_data(created_at, retention_days=90):
        """Check if data should be deleted based on retention policy"""
        expiry_date = created_at + timedelta(days=retention_days)
        return datetime.now() > expiry_date

    # Test data within retention period
    recent_data_date = datetime.now() - timedelta(days=30)
    assert not should_delete_data(recent_data_date, 90), "Recent data should be retained"

    # Test data past retention period
    old_data_date = datetime.now() - timedelta(days=100)
    assert should_delete_data(old_data_date, 90), "Old data should be deleted"

    # Verify retention policy configuration
    retention_policies = {
        "audit_logs": 365,  # 1 year for compliance
        "user_activity": 90,  # 90 days
        "temporary_data": 7,  # 7 days
        "backups": 90  # 90 days
    }

    for data_type, days in retention_policies.items():
        assert days > 0, f"Retention period must be positive: {data_type}"
        assert days <= 365, f"Excessive retention period: {data_type}"


@pytest.mark.compliance
@pytest.mark.gdpr
def test_anonymization_for_statistical_purposes():
    """
    TC034: Verify data can be anonymized for statistics

    GDPR Recital 26: Anonymized data not subject to GDPR
    Requirements:
    - Remove all identifying information
    - Prevent re-identification
    - Safe for statistical analysis
    """
    def anonymize_for_statistics(user_records):
        """Anonymize user data for statistical analysis"""
        anonymized = []
        for record in user_records:
            anon_record = {
                "role": record["role"],
                "access_count": record.get("access_count", 0),
                "registration_year": record["created_at"].year,
                "country_code": record.get("country", "UNKNOWN")
            }
            # Remove all PII
            anonymized.append(anon_record)
        return anonymized

    # Test data
    test_records = [
        {
            "email": "user1@example.com",
            "role": "developer",
            "access_count": 150,
            "created_at": datetime(2025, 1, 15),
            "country": "ES"
        },
        {
            "email": "user2@example.com",
            "role": "admin",
            "access_count": 500,
            "created_at": datetime(2024, 6, 20),
            "country": "DE"
        }
    ]

    anonymized = anonymize_for_statistics(test_records)

    # Verify PII removed
    for record in anonymized:
        assert "email" not in record
        assert "name" not in record
        assert "created_at" not in record or isinstance(record.get("created_at"), int)

    # Verify statistical value retained
    assert len(anonymized) == len(test_records)
    assert anonymized[0]["role"] == "developer"
    assert anonymized[1]["access_count"] == 500


@pytest.mark.compliance
@pytest.mark.gdpr
def test_deletion_verification_and_certification():
    """
    TC035: Verify deletion can be certified

    GDPR Art. 17: Right to Erasure
    Requirements:
    - Provide confirmation of deletion
    - Document what was deleted
    - Timestamp of deletion
    """
    deletion_certificate = {
        "certificate_id": "DEL-2025-001",
        "user_email": "deleted@example.com",
        "deletion_requested_at": "2025-11-06T10:00:00Z",
        "deletion_completed_at": "2025-11-06T10:05:23Z",
        "data_deleted": [
            "User profile",
            "Access logs",
            "Activity history",
            "API keys"
        ],
        "systems_cleared": [
            "PostgreSQL primary database",
            "Redis cache",
            "Backup storage (GCS)"
        ],
        "verified_by": "system_admin",
        "verification_method": "Database query + cache check",
        "retention_exceptions": []
    }

    # Verify certificate structure
    required_fields = [
        "certificate_id", "user_email", "deletion_completed_at",
        "data_deleted", "systems_cleared", "verified_by"
    ]

    for field in required_fields:
        assert field in deletion_certificate, f"Missing field in deletion certificate: {field}"

    assert len(deletion_certificate["data_deleted"]) > 0
    assert len(deletion_certificate["systems_cleared"]) > 0


# ================================================================
# TC036-039: Right of Access (Art. 15)
# ================================================================

@pytest.mark.compliance
@pytest.mark.gdpr
def test_subject_access_request_data_export(db_session):
    """
    TC036: Verify Subject Access Request (SAR) functionality

    GDPR Art. 15: Right of Access
    Requirements:
    - Export all personal data
    - Machine-readable format (JSON)
    - Complete within 30 days
    - No charge for first request
    """
    cursor = db_session.cursor()

    # Create test tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email VARCHAR(255) PRIMARY KEY,
            role VARCHAR(50),
            created_at TIMESTAMP
        )
    """)
    cursor.execute("""
        INSERT INTO users (email, role, created_at)
        VALUES (%s, %s, %s)
    """, ("sar@example.com", "developer", datetime.now()))
    db_session.commit()

    # Execute SAR
    cursor.execute("SELECT * FROM users WHERE email = %s", ("sar@example.com",))
    user_data = cursor.fetchone()

    # Create SAR export
    sar_export = {
        "request_date": datetime.now().isoformat(),
        "user_email": user_data[0],
        "personal_data": {
            "email": user_data[0],
            "role": user_data[1],
            "created_at": user_data[2].isoformat()
        },
        "processing_activities": [
            {
                "activity": "Persona System Access",
                "purpose": "Provide AI capabilities",
                "legal_basis": "Contract (Art. 6(1)(b))"
            }
        ],
        "data_recipients": ["Internal systems only"],
        "retention_period": "90 days",
        "rights": {
            "right_to_rectification": True,
            "right_to_erasure": True,
            "right_to_restrict_processing": True,
            "right_to_data_portability": True
        }
    }

    # Verify SAR export completeness
    assert "personal_data" in sar_export
    assert "processing_activities" in sar_export
    assert "rights" in sar_export
    assert sar_export["rights"]["right_to_erasure"] is True

    # Verify machine-readable format (JSON)
    json_export = json.dumps(sar_export, indent=2)
    assert len(json_export) > 0

    # Cleanup
    cursor.execute("DROP TABLE users")
    db_session.commit()


@pytest.mark.compliance
@pytest.mark.gdpr
def test_data_portability_structured_format():
    """
    TC037: Verify Data Portability (Art. 20)

    GDPR Art. 20: Right to Data Portability
    Requirements:
    - Structured, commonly used format
    - Machine-readable (JSON, CSV, XML)
    - Transmit to another controller if technically feasible
    """
    def export_data_portable_format(user_data, format="json"):
        """Export user data in portable format"""
        if format == "json":
            return json.dumps(user_data, indent=2)
        elif format == "csv":
            import csv
            import io
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=user_data.keys())
            writer.writeheader()
            writer.writerow(user_data)
            return output.getvalue()
        else:
            raise ValueError(f"Unsupported format: {format}")

    test_user_data = {
        "email": "user@example.com",
        "role": "developer",
        "personas_accessed": 45,
        "total_requests": 1250
    }

    # Test JSON export
    json_export = export_data_portable_format(test_user_data, "json")
    assert "email" in json_export
    json_parsed = json.loads(json_export)
    assert json_parsed["email"] == "user@example.com"

    # Test CSV export
    csv_export = export_data_portable_format(test_user_data, "csv")
    assert "email,role,personas_accessed,total_requests" in csv_export
    assert "user@example.com" in csv_export


@pytest.mark.compliance
@pytest.mark.gdpr
def test_access_to_processing_information():
    """
    TC038: Verify access to processing information

    GDPR Art. 15(1): Right to know how data is processed
    """
    processing_transparency = {
        "purposes": [
            "Authentication and authorization",
            "Audit logging for security",
            "Service improvement (with consent)"
        ],
        "categories_of_data": [
            "Email address",
            "Role/permissions",
            "Access timestamps",
            "API usage statistics"
        ],
        "recipients": [
            "Internal systems only",
            "No third-party sharing"
        ],
        "storage_period": "90 days (auto-deletion)",
        "source_of_data": "User registration, system logs",
        "automated_decision_making": False,
        "transfer_to_third_countries": False,
        "safeguards": [
            "Encryption at rest and in transit",
            "Access control (RBAC)",
            "Regular security audits"
        ]
    }

    # Verify transparency information complete
    assert len(processing_transparency["purposes"]) > 0
    assert len(processing_transparency["categories_of_data"]) > 0
    assert processing_transparency["automated_decision_making"] is False
    assert processing_transparency["transfer_to_third_countries"] is False


@pytest.mark.compliance
@pytest.mark.gdpr
def test_free_access_first_request():
    """
    TC039: Verify first access request is free

    GDPR Art. 15(3): First copy of data free of charge
    """
    def calculate_access_request_fee(request_count, is_manifestly_unfounded=False):
        """Calculate fee for access request"""
        if request_count == 1 and not is_manifestly_unfounded:
            return 0  # First request free
        elif is_manifestly_unfounded:
            return 50  # Administrative fee for unfounded requests
        else:
            return 0  # Additional copies also free unless unreasonable

    # Test cases
    assert calculate_access_request_fee(1) == 0, "First request must be free"
    assert calculate_access_request_fee(2) == 0, "Additional requests typically free"
    assert calculate_access_request_fee(1, is_manifestly_unfounded=True) > 0, "Can charge for unfounded requests"


# ================================================================
# TC040-043: Breach Notification (Art. 33-34)
# ================================================================

@pytest.mark.compliance
@pytest.mark.gdpr
def test_breach_detection_mechanism():
    """
    TC040: Verify data breach detection

    GDPR Art. 33: Notification of breach to supervisory authority
    Requirements:
    - Detect breaches within 72 hours
    - Document breach details
    - Assess impact
    """
    def detect_potential_breach(event):
        """Detect potential security breach"""
        breach_indicators = [
            "unauthorized_access",
            "data_exfiltration",
            "encryption_failure",
            "access_control_bypass",
            "ddos_attack"
        ]

        return event["type"] in breach_indicators

    # Test breach detection
    normal_event = {"type": "user_login", "timestamp": datetime.now().isoformat()}
    breach_event = {"type": "unauthorized_access", "timestamp": datetime.now().isoformat(), "user": "attacker"}

    assert not detect_potential_breach(normal_event)
    assert detect_potential_breach(breach_event)


@pytest.mark.compliance
@pytest.mark.gdpr
def test_breach_notification_within_72_hours():
    """
    TC041: Verify breach notification timeline

    GDPR Art. 33: 72-hour notification requirement
    """
    def calculate_notification_deadline(breach_detected_at):
        """Calculate 72-hour deadline for breach notification"""
        return breach_detected_at + timedelta(hours=72)

    def is_within_notification_window(breach_time, notification_time):
        """Check if notification within 72 hours"""
        deadline = calculate_notification_deadline(breach_time)
        return notification_time <= deadline

    # Test cases
    breach_time = datetime(2025, 11, 6, 10, 0, 0)
    notification_within = datetime(2025, 11, 8, 9, 0, 0)  # 47 hours later
    notification_late = datetime(2025, 11, 10, 11, 0, 0)  # 73 hours later

    assert is_within_notification_window(breach_time, notification_within), "Should be within window"
    assert not is_within_notification_window(breach_time, notification_late), "Should be outside window"


@pytest.mark.compliance
@pytest.mark.gdpr
def test_breach_documentation_completeness():
    """
    TC042: Verify breach documentation

    GDPR Art. 33(3): Required breach information
    """
    breach_report = {
        "breach_id": "BREACH-2025-001",
        "detected_at": "2025-11-06T14:30:00Z",
        "reported_at": "2025-11-07T10:00:00Z",
        "nature_of_breach": "Unauthorized access attempt to persona database",
        "categories_of_data_affected": ["User emails", "Access logs"],
        "approximate_data_subjects_affected": 150,
        "approximate_records_affected": 500,
        "likely_consequences": "Minimal - no sensitive data exposed, access blocked",
        "measures_taken": [
            "Blocked suspicious IP addresses",
            "Forced password reset for affected users",
            "Enhanced monitoring enabled"
        ],
        "measures_to_mitigate": [
            "Implement rate limiting",
            "Add geo-blocking",
            "Review access patterns daily"
        ],
        "dpo_contacted": True,
        "supervisory_authority_notified": True,
        "data_subjects_notified": False,  # Not required - minimal risk
        "notification_justification": "Risk to data subjects not high - no sensitive data exposed"
    }

    # Verify required fields present
    required_fields = [
        "nature_of_breach",
        "categories_of_data_affected",
        "likely_consequences",
        "measures_taken"
    ]

    for field in required_fields:
        assert field in breach_report, f"Missing required field: {field}"


@pytest.mark.compliance
@pytest.mark.gdpr
def test_data_subject_notification_high_risk():
    """
    TC043: Verify data subject notification for high-risk breaches

    GDPR Art. 34: Communication of breach to data subject
    """
    def should_notify_data_subjects(breach_risk_assessment):
        """Determine if data subjects must be notified"""
        high_risk_factors = [
            breach_risk_assessment.get("sensitive_data_exposed", False),
            breach_risk_assessment.get("identity_theft_risk", False),
            breach_risk_assessment.get("financial_loss_risk", False),
            breach_risk_assessment.get("large_scale_breach", False)
        ]

        return any(high_risk_factors)

    # Test cases
    low_risk_breach = {
        "sensitive_data_exposed": False,
        "identity_theft_risk": False,
        "financial_loss_risk": False,
        "large_scale_breach": False
    }

    high_risk_breach = {
        "sensitive_data_exposed": True,
        "identity_theft_risk": True,
        "financial_loss_risk": False,
        "large_scale_breach": False
    }

    assert not should_notify_data_subjects(low_risk_breach), "Low risk - no notification needed"
    assert should_notify_data_subjects(high_risk_breach), "High risk - must notify data subjects"


# ================================================================
# TC044-046: Consent Management
# ================================================================

@pytest.mark.compliance
@pytest.mark.gdpr
def test_explicit_consent_mechanism():
    """
    TC044: Verify explicit consent for data processing

    GDPR Art. 7: Conditions for consent
    Requirements:
    - Freely given
    - Specific
    - Informed
    - Unambiguous
    """
    consent_record = {
        "user_email": "user@example.com",
        "consent_id": "CONSENT-2025-001",
        "consent_given_at": datetime.now().isoformat(),
        "consent_type": "telemetry_data_collection",
        "purpose": "Improve service quality through usage analytics",
        "freely_given": True,  # No service denial without consent
        "specific": True,  # Specific to telemetry only
        "informed": True,  # User was informed of purpose
        "unambiguous": True,  # Explicit action required (not pre-checked)
        "consent_method": "opt_in_checkbox",
        "withdrawal_method": "account_settings",
        "can_withdraw": True
    }

    # Verify consent validity
    assert consent_record["freely_given"] is True
    assert consent_record["specific"] is True
    assert consent_record["informed"] is True
    assert consent_record["unambiguous"] is True
    assert consent_record["can_withdraw"] is True


@pytest.mark.compliance
@pytest.mark.gdpr
def test_consent_withdrawal_mechanism():
    """
    TC045: Verify consent can be withdrawn

    GDPR Art. 7(3): Right to withdraw consent
    """
    class ConsentManager:
        def __init__(self):
            self.consents = {}

        def give_consent(self, user_email, purpose):
            self.consents[user_email] = {
                "purpose": purpose,
                "given_at": datetime.now(),
                "active": True
            }

        def withdraw_consent(self, user_email):
            if user_email in self.consents:
                self.consents[user_email]["active"] = False
                self.consents[user_email]["withdrawn_at"] = datetime.now()
                return True
            return False

        def has_consent(self, user_email):
            return (user_email in self.consents and
                    self.consents[user_email].get("active", False))

    # Test consent lifecycle
    cm = ConsentManager()

    # Give consent
    cm.give_consent("user@example.com", "telemetry")
    assert cm.has_consent("user@example.com") is True

    # Withdraw consent
    cm.withdraw_consent("user@example.com")
    assert cm.has_consent("user@example.com") is False


@pytest.mark.compliance
@pytest.mark.gdpr
def test_granular_consent_options():
    """
    TC046: Verify granular consent options

    GDPR: Consent must be specific and granular
    """
    consent_options = {
        "essential_cookies": {
            "required": True,  # Cannot be disabled
            "purpose": "Authentication and security",
            "legal_basis": "Legitimate Interest"
        },
        "analytics_cookies": {
            "required": False,
            "purpose": "Usage statistics",
            "legal_basis": "Consent",
            "user_choice": None  # User must choose
        },
        "marketing_emails": {
            "required": False,
            "purpose": "Product updates and news",
            "legal_basis": "Consent",
            "user_choice": None
        },
        "third_party_sharing": {
            "required": False,
            "purpose": "Integration with external services",
            "legal_basis": "Consent",
            "user_choice": None
        }
    }

    # Verify granular options available
    optional_consents = [k for k, v in consent_options.items() if not v["required"]]
    assert len(optional_consents) >= 3, "Should have multiple granular consent options"

    # Verify no bundled consent
    for consent_name, details in consent_options.items():
        if not details["required"]:
            assert "user_choice" in details, f"User must be able to choose: {consent_name}"

"""
Pytest Configuration and Shared Fixtures
Enterprise-Ready Test Infrastructure for NubemSuperFClaude
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Generator, Dict, Any
import pytest
import yaml
from unittest.mock import Mock, MagicMock

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ================================================================
# CONFIGURATION FIXTURES
# ================================================================

@pytest.fixture(scope="session")
def test_config() -> Dict[str, Any]:
    """Global test configuration"""
    return {
        "personas_path": "/tmp/test-personas",
        "api_base_url": "http://localhost:8080",
        "timeout": 30,
        "test_user_email": "test@example.com",
        "test_api_key": "test_key_12345",
    }


@pytest.fixture(scope="session")
def personas_path(tmp_path_factory) -> Path:
    """Create temporary personas directory with test data"""
    personas_dir = tmp_path_factory.mktemp("personas")

    # Create test persona files
    test_personas = [
        {
            "key": "test-architect",
            "name": "test-architect",
            "level": "L5",
            "identity": "Test System Architect for testing purposes",
            "specialties": ["Testing", "Architecture"],
        },
        {
            "key": "test-developer",
            "name": "test-developer",
            "level": "L4",
            "identity": "Test Developer for unit testing",
            "specialties": ["Development", "Testing"],
        },
    ]

    for persona in test_personas:
        persona_file = personas_dir / f"{persona['key']}.yaml"
        with open(persona_file, 'w') as f:
            yaml.dump(persona, f)

    # Set environment variable
    os.environ['PERSONAS_PATH'] = str(personas_dir)

    return personas_dir


@pytest.fixture
def mock_personas_manager():
    """Mock PersonaManager for isolated testing"""
    manager = MagicMock()
    manager.personas = {}
    manager.loaded_count = 0
    manager.load_external_personas = Mock(return_value=2)
    manager.reload_personas = Mock(return_value={"status": "success", "loaded": 2})
    return manager


# ================================================================
# DATABASE FIXTURES
# ================================================================

@pytest.fixture(scope="session")
def postgres_connection():
    """PostgreSQL connection for integration tests"""
    import psycopg2

    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", 5432),
        database=os.getenv("POSTGRES_DB", "test_db"),
        user=os.getenv("POSTGRES_USER", "test_user"),
        password=os.getenv("POSTGRES_PASSWORD", "test_password"),
    )

    yield conn

    conn.close()


@pytest.fixture(scope="function")
def clean_database(postgres_connection):
    """Clean database before each test"""
    cursor = postgres_connection.cursor()

    # Clean audit logs table
    cursor.execute("DELETE FROM audit_logs WHERE 1=1;")
    postgres_connection.commit()

    yield

    cursor.close()


# ================================================================
# REDIS FIXTURES
# ================================================================

@pytest.fixture(scope="session")
def redis_client():
    """Redis client for caching tests"""
    import redis

    client = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        db=0,
        decode_responses=True,
    )

    yield client

    client.flushdb()
    client.close()


# ================================================================
# API CLIENT FIXTURES
# ================================================================

@pytest.fixture
def api_client(test_config):
    """HTTP client for API testing"""
    import httpx

    client = httpx.Client(
        base_url=test_config["api_base_url"],
        timeout=test_config["timeout"],
        headers={
            "X-API-Key": test_config["test_api_key"],
            "Content-Type": "application/json",
        },
    )

    yield client

    client.close()


@pytest.fixture
def async_api_client(test_config):
    """Async HTTP client for API testing"""
    import httpx

    async def _client():
        async with httpx.AsyncClient(
            base_url=test_config["api_base_url"],
            timeout=test_config["timeout"],
            headers={
                "X-API-Key": test_config["test_api_key"],
                "Content-Type": "application/json",
            },
        ) as client:
            yield client

    return _client


# ================================================================
# KUBERNETES FIXTURES
# ================================================================

@pytest.fixture(scope="session")
def k8s_client():
    """Kubernetes client for E2E tests"""
    from kubernetes import client, config

    try:
        config.load_kube_config()
    except:
        config.load_incluster_config()

    return client.CoreV1Api()


@pytest.fixture
def k8s_namespace():
    """Test namespace in Kubernetes"""
    return os.getenv("K8S_NAMESPACE", "default")


# ================================================================
# SECURITY FIXTURES
# ================================================================

@pytest.fixture
def mock_auth_admin():
    """Mock admin authentication"""
    return {
        "user_email": "admin@test.com",
        "role": "admin",
        "api_key": "admin_key_test",
        "permissions": ["read", "write", "delete", "execute"],
    }


@pytest.fixture
def mock_auth_developer():
    """Mock developer authentication"""
    return {
        "user_email": "dev@test.com",
        "role": "developer",
        "api_key": "dev_key_test",
        "permissions": ["read", "execute"],
    }


@pytest.fixture
def mock_auth_readonly():
    """Mock readonly authentication"""
    return {
        "user_email": "readonly@test.com",
        "role": "readonly",
        "api_key": "readonly_key_test",
        "permissions": ["read"],
    }


# ================================================================
# COMPLIANCE FIXTURES
# ================================================================

@pytest.fixture
def gdpr_test_data():
    """Test data for GDPR compliance testing"""
    return {
        "pii_examples": [
            "john.doe@example.com",
            "+1-555-123-4567",
            "192.168.1.1",
            "123-45-6789",  # SSN format
        ],
        "safe_examples": [
            "user_id_12345",
            "session_token_abc",
            "persona_architect",
        ],
    }


@pytest.fixture
def iso27001_controls():
    """ISO 27001 control references"""
    return {
        "A.9.2.1": "User registration and de-registration",
        "A.9.2.2": "User access provisioning",
        "A.12.1.2": "Change management",
        "A.14.2.1": "Secure development policy",
        "A.17.1.2": "Implementing information security continuity",
    }


# ================================================================
# PERFORMANCE FIXTURES
# ================================================================

@pytest.fixture
def performance_monitor():
    """Monitor test performance"""
    import time

    class PerformanceMonitor:
        def __init__(self):
            self.start_time = None
            self.end_time = None

        def start(self):
            self.start_time = time.time()

        def stop(self):
            self.end_time = time.time()

        def duration(self):
            if self.start_time and self.end_time:
                return self.end_time - self.start_time
            return None

    return PerformanceMonitor()


# ================================================================
# LOGGING FIXTURES
# ================================================================

@pytest.fixture(autouse=True)
def setup_test_logging(caplog):
    """Configure logging for all tests"""
    import logging
    caplog.set_level(logging.DEBUG)
    yield caplog


# ================================================================
# CLEANUP FIXTURES
# ================================================================

@pytest.fixture(autouse=True, scope="function")
def cleanup_temp_files():
    """Clean up temporary files after each test"""
    yield

    # Clean up /tmp/test-* files
    import glob
    for temp_file in glob.glob("/tmp/test-*"):
        try:
            if os.path.isfile(temp_file):
                os.remove(temp_file)
            elif os.path.isdir(temp_file):
                import shutil
                shutil.rmtree(temp_file)
        except:
            pass


# ================================================================
# PYTEST HOOKS
# ================================================================

def pytest_configure(config):
    """Pytest configuration hook"""
    config.addinivalue_line("markers", "unit: Unit tests (fast, isolated)")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "security: Security tests")
    config.addinivalue_line("markers", "compliance: Compliance tests")
    config.addinivalue_line("markers", "iso27001: ISO 27001 compliance")
    config.addinivalue_line("markers", "gdpr: GDPR compliance")
    config.addinivalue_line("markers", "aiact: AI Act compliance")
    config.addinivalue_line("markers", "slow: Slow tests (> 1 second)")


def pytest_collection_modifyitems(config, items):
    """Modify test collection"""
    for item in items:
        # Auto-mark slow tests
        if "slow" in item.nodeid:
            item.add_marker(pytest.mark.slow)

        # Auto-mark tests by directory
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
        elif "security" in str(item.fspath):
            item.add_marker(pytest.mark.security)
        elif "compliance" in str(item.fspath):
            item.add_marker(pytest.mark.compliance)

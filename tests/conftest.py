"""
Pytest configuration and fixtures
"""
import os
import sys
import pytest

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.fixture(scope="session")
def test_env():
    """Setup test environment variables"""
    os.environ['NC_ENV'] = 'test'
    os.environ['NC_DEBUG'] = 'false'
    os.environ['SECRET_MANAGER_PROJECT'] = 'test-project'
    yield
    # Cleanup
    del os.environ['NC_ENV']


@pytest.fixture
def mock_secrets_manager(monkeypatch):
    """Mock SecretsManager for testing"""
    class MockSecretsManager:
        def __init__(self):
            self.project_id = 'test-project'
            self.use_secret_manager = False
            self.client = None

        def get_secret(self, secret_name, user_email=None):
            return f"mock_value_for_{secret_name}"

    monkeypatch.setattr('core.secrets_manager.SecretsManager', MockSecretsManager)
    return MockSecretsManager()

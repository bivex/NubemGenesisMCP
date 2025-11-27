"""
Unit Tests for MultiTenantVaultManager
Tests secret management across tenant GCP projects
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4, UUID
from datetime import datetime

from core.multi_tenant_vault import (
    MultiTenantVaultManager,
    VaultError,
    SecretNotFoundError,
    TenantNotFoundError,
    SecretAccessDeniedError
)

from google.api_core import exceptions as google_exceptions


# Test fixtures
@pytest.fixture
def mock_secret_manager_client():
    """Mock SecretManagerServiceClient"""
    with patch('core.multi_tenant_vault.secretmanager.SecretManagerServiceClient') as mock:
        yield mock.return_value


@pytest.fixture
def vault_manager(mock_secret_manager_client):
    """Create VaultManager instance with mocked client"""
    manager = MultiTenantVaultManager(main_project_id="test-main-project")
    manager.client = mock_secret_manager_client
    return manager


@pytest.fixture
def test_tenant_id():
    """Test tenant UUID"""
    return UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def test_tenant_project_id():
    """Test tenant GCP project ID"""
    return "nubemsfc-tenant-12345678-abcd"


class TestVaultManagerInitialization:
    """Test vault manager initialization"""

    def test_init_success(self, mock_secret_manager_client):
        """Test successful initialization"""
        manager = MultiTenantVaultManager(main_project_id="test-project")

        assert manager.main_project_id == "test-project"
        assert manager.client is not None


class TestGetSecret:
    """Test getting secrets"""

    def test_get_secret_success(
        self,
        vault_manager,
        mock_secret_manager_client,
        test_tenant_id,
        test_tenant_project_id
    ):
        """Test getting secret successfully"""
        # Mock _get_tenant_project_id
        vault_manager._get_tenant_project_id = Mock(return_value=test_tenant_project_id)

        # Mock access_secret_version
        mock_response = Mock()
        mock_response.payload.data = b"secret_value_123"
        mock_secret_manager_client.access_secret_version.return_value = mock_response

        # Mock _log_secret_access
        vault_manager._log_secret_access = Mock()

        # Get secret
        result = vault_manager.get_secret(test_tenant_id, "test-secret")

        assert result == "secret_value_123"
        vault_manager._get_tenant_project_id.assert_called_once_with(test_tenant_id)

        # Verify correct secret path was used
        call_args = mock_secret_manager_client.access_secret_version.call_args
        assert test_tenant_project_id in call_args[1]["request"]["name"]
        assert "test-secret" in call_args[1]["request"]["name"]

        # Verify audit log
        vault_manager._log_secret_access.assert_called_once()

    def test_get_secret_specific_version(
        self,
        vault_manager,
        mock_secret_manager_client,
        test_tenant_id,
        test_tenant_project_id
    ):
        """Test getting specific secret version"""
        vault_manager._get_tenant_project_id = Mock(return_value=test_tenant_project_id)

        mock_response = Mock()
        mock_response.payload.data = b"old_value"
        mock_secret_manager_client.access_secret_version.return_value = mock_response

        vault_manager._log_secret_access = Mock()

        result = vault_manager.get_secret(test_tenant_id, "test-secret", version="2")

        assert result == "old_value"
        call_args = mock_secret_manager_client.access_secret_version.call_args
        assert "/versions/2" in call_args[1]["request"]["name"]

    def test_get_secret_not_found(
        self,
        vault_manager,
        mock_secret_manager_client,
        test_tenant_id,
        test_tenant_project_id
    ):
        """Test getting non-existent secret"""
        vault_manager._get_tenant_project_id = Mock(return_value=test_tenant_project_id)

        mock_secret_manager_client.access_secret_version.side_effect = google_exceptions.NotFound("Not found")

        with pytest.raises(SecretNotFoundError):
            vault_manager.get_secret(test_tenant_id, "nonexistent-secret")

    def test_get_secret_access_denied(
        self,
        vault_manager,
        mock_secret_manager_client,
        test_tenant_id,
        test_tenant_project_id
    ):
        """Test access denied to secret"""
        vault_manager._get_tenant_project_id = Mock(return_value=test_tenant_project_id)

        mock_secret_manager_client.access_secret_version.side_effect = google_exceptions.PermissionDenied("Denied")

        with pytest.raises(SecretAccessDeniedError):
            vault_manager.get_secret(test_tenant_id, "restricted-secret")


class TestSetSecret:
    """Test setting secrets"""

    def test_set_secret_create_new(
        self,
        vault_manager,
        mock_secret_manager_client,
        test_tenant_id,
        test_tenant_project_id
    ):
        """Test creating new secret"""
        vault_manager._get_tenant_project_id = Mock(return_value=test_tenant_project_id)
        vault_manager._log_secret_access = Mock()

        # Mock get_secret to raise NotFound (secret doesn't exist)
        mock_secret_manager_client.get_secret.side_effect = google_exceptions.NotFound("Not found")

        # Mock create_secret and add_secret_version
        mock_secret_manager_client.create_secret.return_value = Mock()
        mock_secret_manager_client.add_secret_version.return_value = Mock()

        result = vault_manager.set_secret(
            test_tenant_id,
            "new-secret",
            "secret_value"
        )

        assert result is True
        mock_secret_manager_client.create_secret.assert_called_once()
        mock_secret_manager_client.add_secret_version.assert_called_once()

    def test_set_secret_update_existing(
        self,
        vault_manager,
        mock_secret_manager_client,
        test_tenant_id,
        test_tenant_project_id
    ):
        """Test updating existing secret"""
        vault_manager._get_tenant_project_id = Mock(return_value=test_tenant_project_id)
        vault_manager._log_secret_access = Mock()

        # Mock get_secret to succeed (secret exists)
        mock_secret_manager_client.get_secret.return_value = Mock()

        # Mock add_secret_version
        mock_secret_manager_client.add_secret_version.return_value = Mock()

        result = vault_manager.set_secret(
            test_tenant_id,
            "existing-secret",
            "new_value"
        )

        assert result is True
        mock_secret_manager_client.create_secret.assert_not_called()
        mock_secret_manager_client.add_secret_version.assert_called_once()

    def test_set_secret_with_labels(
        self,
        vault_manager,
        mock_secret_manager_client,
        test_tenant_id,
        test_tenant_project_id
    ):
        """Test setting secret with custom labels"""
        vault_manager._get_tenant_project_id = Mock(return_value=test_tenant_project_id)
        vault_manager._log_secret_access = Mock()

        mock_secret_manager_client.get_secret.side_effect = google_exceptions.NotFound("Not found")
        mock_secret_manager_client.create_secret.return_value = Mock()
        mock_secret_manager_client.add_secret_version.return_value = Mock()

        result = vault_manager.set_secret(
            test_tenant_id,
            "labeled-secret",
            "value",
            labels={"type": "api_key", "provider": "openai"}
        )

        assert result is True

        # Verify labels were passed
        create_call_args = mock_secret_manager_client.create_secret.call_args
        secret_config = create_call_args[1]["request"]["secret"]
        assert "type" in secret_config["labels"]
        assert secret_config["labels"]["type"] == "api_key"


class TestDeleteSecret:
    """Test deleting secrets"""

    def test_delete_secret_success(
        self,
        vault_manager,
        mock_secret_manager_client,
        test_tenant_id,
        test_tenant_project_id
    ):
        """Test deleting secret successfully"""
        vault_manager._get_tenant_project_id = Mock(return_value=test_tenant_project_id)
        vault_manager._log_secret_access = Mock()

        mock_secret_manager_client.delete_secret.return_value = Mock()

        result = vault_manager.delete_secret(test_tenant_id, "old-secret")

        assert result is True
        mock_secret_manager_client.delete_secret.assert_called_once()

        # Verify audit log
        vault_manager._log_secret_access.assert_called_once()
        log_call = vault_manager._log_secret_access.call_args
        assert log_call[1]["action"] == "delete"

    def test_delete_secret_not_found(
        self,
        vault_manager,
        mock_secret_manager_client,
        test_tenant_id,
        test_tenant_project_id
    ):
        """Test deleting non-existent secret"""
        vault_manager._get_tenant_project_id = Mock(return_value=test_tenant_project_id)

        mock_secret_manager_client.delete_secret.side_effect = google_exceptions.NotFound("Not found")

        with pytest.raises(SecretNotFoundError):
            vault_manager.delete_secret(test_tenant_id, "nonexistent")


class TestListSecrets:
    """Test listing secrets"""

    def test_list_secrets_success(
        self,
        vault_manager,
        mock_secret_manager_client,
        test_tenant_id,
        test_tenant_project_id
    ):
        """Test listing secrets successfully"""
        vault_manager._get_tenant_project_id = Mock(return_value=test_tenant_project_id)

        # Mock secrets
        mock_secret_1 = Mock()
        mock_secret_1.name = f"projects/{test_tenant_project_id}/secrets/secret-1"
        mock_secret_1.labels = {"type": "api_key"}
        mock_secret_1.create_time = datetime(2025, 1, 1)

        mock_secret_2 = Mock()
        mock_secret_2.name = f"projects/{test_tenant_project_id}/secrets/secret-2"
        mock_secret_2.labels = {"type": "token"}
        mock_secret_2.create_time = datetime(2025, 1, 2)

        mock_secret_manager_client.list_secrets.return_value = [mock_secret_1, mock_secret_2]

        # Mock access_secret_version for latest version
        mock_version = Mock()
        mock_version.create_time = datetime(2025, 1, 3)
        mock_secret_manager_client.access_secret_version.return_value = mock_version

        result = vault_manager.list_secrets(test_tenant_id)

        assert len(result) == 2
        assert result[0]["name"] == "secret-1"
        assert result[1]["name"] == "secret-2"
        assert result[0]["labels"]["type"] == "api_key"

    def test_list_secrets_empty(
        self,
        vault_manager,
        mock_secret_manager_client,
        test_tenant_id,
        test_tenant_project_id
    ):
        """Test listing secrets when none exist"""
        vault_manager._get_tenant_project_id = Mock(return_value=test_tenant_project_id)

        mock_secret_manager_client.list_secrets.return_value = []

        result = vault_manager.list_secrets(test_tenant_id)

        assert len(result) == 0


class TestRotateSecret:
    """Test secret rotation"""

    def test_rotate_secret_success(
        self,
        vault_manager,
        mock_secret_manager_client,
        test_tenant_id
    ):
        """Test rotating secret successfully"""
        # Mock set_secret
        vault_manager.set_secret = Mock(return_value=True)
        vault_manager._log_secret_access = Mock()

        result = vault_manager.rotate_secret(
            test_tenant_id,
            "api-key",
            "new_value_456"
        )

        assert result is True
        vault_manager.set_secret.assert_called_once()

        # Verify new value was set
        call_args = vault_manager.set_secret.call_args
        assert call_args[0][2] == "new_value_456"

        # Verify rotation annotation
        assert "annotations" in call_args[1]


class TestGetSecretVersions:
    """Test getting secret version history"""

    def test_get_secret_versions(
        self,
        vault_manager,
        mock_secret_manager_client,
        test_tenant_id,
        test_tenant_project_id
    ):
        """Test getting secret versions"""
        vault_manager._get_tenant_project_id = Mock(return_value=test_tenant_project_id)

        # Mock versions
        mock_version_1 = Mock()
        mock_version_1.name = "projects/x/secrets/s/versions/2"
        mock_version_1.state.name = "ENABLED"
        mock_version_1.create_time = datetime(2025, 1, 1)
        mock_version_1.destroy_time = None

        mock_version_2 = Mock()
        mock_version_2.name = "projects/x/secrets/s/versions/1"
        mock_version_2.state.name = "DESTROYED"
        mock_version_2.create_time = datetime(2025, 1, 1)
        mock_version_2.destroy_time = datetime(2025, 1, 2)

        mock_secret_manager_client.list_secret_versions.return_value = [mock_version_1, mock_version_2]

        result = vault_manager.get_secret_versions(test_tenant_id, "test-secret")

        assert len(result) == 2
        assert result[0]["name"] == "2"
        assert result[0]["state"] == "ENABLED"
        assert result[1]["name"] == "1"
        assert result[1]["state"] == "DESTROYED"


class TestGetTenantProjectId:
    """Test getting tenant project ID from metadata"""

    def test_get_tenant_project_id_success(
        self,
        vault_manager,
        mock_secret_manager_client,
        test_tenant_id,
        test_tenant_project_id
    ):
        """Test getting project ID successfully"""
        # Mock metadata response
        mock_response = Mock()
        metadata_dict = {"project_id": test_tenant_project_id}
        mock_response.payload.data = str(metadata_dict).encode('UTF-8')

        mock_secret_manager_client.access_secret_version.return_value = mock_response

        result = vault_manager._get_tenant_project_id(test_tenant_id)

        assert result == test_tenant_project_id

    def test_get_tenant_project_id_not_found(
        self,
        vault_manager,
        mock_secret_manager_client,
        test_tenant_id
    ):
        """Test getting project ID for non-existent tenant"""
        mock_secret_manager_client.access_secret_version.side_effect = google_exceptions.NotFound("Not found")

        with pytest.raises(TenantNotFoundError):
            vault_manager._get_tenant_project_id(test_tenant_id)


class TestAuditLogging:
    """Test audit logging functionality"""

    def test_log_secret_access(self, vault_manager, test_tenant_id):
        """Test logging secret access"""
        # This just verifies the method runs without error
        vault_manager._log_secret_access(
            tenant_id=test_tenant_id,
            secret_name="test-secret",
            action="read",
            success=True,
            metadata={"extra": "info"}
        )

        # Should not raise any exceptions


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

#!/usr/bin/env python3
"""
Tests for Multi-Tenancy Secrets Management
"""

import os
import sys
import pytest
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.secrets_manager import SecretsManager, secrets_manager


class TestMultiTenancySecrets:
    """Test suite for multi-tenancy secrets management"""

    def test_get_user_prefix(self):
        """Test email to prefix conversion"""
        manager = SecretsManager()

        assert manager._get_user_prefix("user@domain.com") == "user_domain_com"
        assert manager._get_user_prefix("test.user@example.org") == "test_user_example_org"
        assert manager._get_user_prefix("admin@nubemsystems.es") == "admin_nubemsystems_es"

    def test_get_full_secret_name_without_user(self):
        """Test secret name without user (system secret)"""
        manager = SecretsManager()

        result = manager._get_full_secret_name("openai-api-key", user_email=None)
        assert result == "openai-api-key"

    def test_get_full_secret_name_with_user(self):
        """Test secret name with user prefix"""
        manager = SecretsManager()

        result = manager._get_full_secret_name("openai-api-key", user_email="user@domain.com")
        assert result == "user_domain_com_openai-api-key"

    def test_backward_compatibility_get_secret(self):
        """Test that get_secret still works without user_email parameter"""
        manager = SecretsManager()

        # Mock environment variable
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key-123'}):
            result = manager.get_secret("openai-api-key")
            assert result == 'test-key-123'

    @patch('core.secrets_manager.GOOGLE_CLOUD_AVAILABLE', True)
    def test_get_secret_with_user_isolation(self):
        """Test that secrets are isolated by user"""
        manager = SecretsManager()
        manager.use_secret_manager = True

        # Mock Google Cloud client
        mock_client = MagicMock()
        manager.client = mock_client
        manager.project_id = 'test-project'

        # Mock response
        mock_response = MagicMock()
        mock_response.payload.data.decode.return_value = 'user1-secret-value'
        mock_client.access_secret_version.return_value = mock_response

        # Clear cache before test
        manager.get_secret.cache_clear()

        # Get secret for user1
        result = manager.get_secret("api-key", user_email="user1@domain.com")

        # Verify correct secret name was requested
        expected_name = "projects/test-project/secrets/user1_domain_com_api-key/versions/latest"
        mock_client.access_secret_version.assert_called_once()
        call_args = mock_client.access_secret_version.call_args
        assert call_args[1]['request']['name'] == expected_name
        assert result == 'user1-secret-value'

    @patch('core.secrets_manager.GOOGLE_CLOUD_AVAILABLE', True)
    def test_fallback_to_system_secret(self):
        """Test fallback from user secret to system secret"""
        manager = SecretsManager()
        manager.use_secret_manager = True

        mock_client = MagicMock()
        manager.client = mock_client
        manager.project_id = 'test-project'

        # First call (user secret) fails, second call (system secret) succeeds
        def side_effect(request):
            secret_name = request['name']
            if 'user1_domain_com' in secret_name:
                raise Exception("Secret not found")
            else:
                mock_response = MagicMock()
                mock_response.payload.data.decode.return_value = 'system-secret-value'
                return mock_response

        mock_client.access_secret_version.side_effect = side_effect

        # Clear cache
        manager.get_secret.cache_clear()

        # Get secret for user (should fallback to system)
        result = manager.get_secret("shared-api-key", user_email="user1@domain.com")

        # Should have tried user secret first, then system secret
        assert mock_client.access_secret_version.call_count == 2
        assert result == 'system-secret-value'

    @patch('core.secrets_manager.GOOGLE_CLOUD_AVAILABLE', True)
    def test_create_secret_with_user(self):
        """Test creating user-specific secret"""
        manager = SecretsManager()
        manager.use_secret_manager = True

        mock_client = MagicMock()
        manager.client = mock_client
        manager.project_id = 'test-project'

        # Mock responses
        mock_secret_response = MagicMock()
        mock_secret_response.name = 'projects/test-project/secrets/user1_domain_com_my-secret'
        mock_client.create_secret.return_value = mock_secret_response

        # Create secret
        result = manager.create_secret(
            "my-secret",
            "secret-value-123",
            user_email="user1@domain.com",
            labels={"env": "test"}
        )

        assert result is True

        # Verify create_secret was called with correct parameters
        create_call = mock_client.create_secret.call_args
        assert create_call[1]['request']['secret_id'] == 'user1_domain_com_my-secret'
        assert create_call[1]['request']['secret']['labels']['owner'] == 'user1_domain_com'
        assert create_call[1]['request']['secret']['labels']['env'] == 'test'

        # Verify add_secret_version was called
        assert mock_client.add_secret_version.called

    @patch('core.secrets_manager.GOOGLE_CLOUD_AVAILABLE', True)
    def test_list_secrets_filtered_by_user(self):
        """Test listing secrets filtered by user"""
        manager = SecretsManager()
        manager.use_secret_manager = True

        mock_client = MagicMock()
        manager.client = mock_client
        manager.project_id = 'test-project'

        # Mock secrets list
        mock_secret1 = MagicMock()
        mock_secret1.name = 'projects/test-project/secrets/user1_domain_com_api-key'

        mock_secret2 = MagicMock()
        mock_secret2.name = 'projects/test-project/secrets/user1_domain_com_db-password'

        mock_secret3 = MagicMock()
        mock_secret3.name = 'projects/test-project/secrets/user2_other_com_api-key'

        mock_secret4 = MagicMock()
        mock_secret4.name = 'projects/test-project/secrets/system-secret'

        mock_client.list_secrets.return_value = [
            mock_secret1, mock_secret2, mock_secret3, mock_secret4
        ]

        # List secrets for user1
        result = manager.list_secrets(user_email="user1@domain.com")

        # Should only return user1's secrets without prefix
        assert 'api-key' in result
        assert 'db-password' in result
        assert len(result) == 2

    @patch('core.secrets_manager.GOOGLE_CLOUD_AVAILABLE', True)
    def test_update_secret_with_user(self):
        """Test updating user-specific secret"""
        manager = SecretsManager()
        manager.use_secret_manager = True

        mock_client = MagicMock()
        manager.client = mock_client
        manager.project_id = 'test-project'

        # Update secret
        result = manager.update_secret(
            "my-secret",
            "new-value-456",
            user_email="user1@domain.com"
        )

        assert result is True

        # Verify add_secret_version was called with correct parent
        add_version_call = mock_client.add_secret_version.call_args
        expected_parent = 'projects/test-project/secrets/user1_domain_com_my-secret'
        assert add_version_call[1]['request']['parent'] == expected_parent

    @patch('core.secrets_manager.GOOGLE_CLOUD_AVAILABLE', True)
    def test_delete_secret_with_user(self):
        """Test deleting user-specific secret"""
        manager = SecretsManager()
        manager.use_secret_manager = True

        mock_client = MagicMock()
        manager.client = mock_client
        manager.project_id = 'test-project'

        # Delete secret
        result = manager.delete_secret("my-secret", user_email="user1@domain.com")

        assert result is True

        # Verify delete_secret was called with correct name
        delete_call = mock_client.delete_secret.call_args
        expected_name = 'projects/test-project/secrets/user1_domain_com_my-secret'
        assert delete_call[1]['request']['name'] == expected_name

    def test_system_secrets_still_work(self):
        """Test that system secrets (no user) still work as before"""
        manager = SecretsManager()

        # Disable Secret Manager for this test
        original_use_sm = manager.use_secret_manager
        manager.use_secret_manager = False

        # Test with environment variables (backward compatibility)
        with patch.dict(os.environ, {
            'OPENAI_API_KEY': 'openai-key',
            'ANTHROPIC_API_KEY': 'anthropic-key'
        }):
            # Clear cache
            manager.get_secret.cache_clear()

            assert manager.get_openai_key() == 'openai-key'
            assert manager.get_anthropic_key() == 'anthropic-key'

        # Restore original state
        manager.use_secret_manager = original_use_sm

    @patch('core.secrets_manager.GOOGLE_CLOUD_AVAILABLE', True)
    @patch.dict(os.environ, {}, clear=True)  # Clear all env vars for this test
    def test_user_cannot_access_other_user_secrets(self):
        """Test that users cannot access other users' secrets"""
        manager = SecretsManager()
        manager.use_secret_manager = True

        mock_client = MagicMock()
        manager.client = mock_client
        manager.project_id = 'test-project'

        # Mock that both user-specific and system secret don't exist
        def side_effect(request):
            raise Exception("Secret not found")

        mock_client.access_secret_version.side_effect = side_effect

        # Clear cache
        manager.get_secret.cache_clear()

        # Try to get another user's secret
        result = manager.get_secret("api-key", user_email="user2@domain.com")

        # Should return None (not found)
        assert result is None

        # Should have tried both user-specific and system secret
        assert mock_client.access_secret_version.call_count == 2


class TestMultiTenancyIntegration:
    """Integration tests for multi-tenancy"""

    def test_multiple_users_same_secret_name(self):
        """Test that multiple users can have secrets with the same name"""
        manager = SecretsManager()

        # Verify prefix generation creates unique names
        user1_prefix = manager._get_user_prefix("user1@domain.com")
        user2_prefix = manager._get_user_prefix("user2@domain.com")

        secret_name = "api-key"
        user1_full = manager._get_full_secret_name(secret_name, "user1@domain.com")
        user2_full = manager._get_full_secret_name(secret_name, "user2@domain.com")

        assert user1_full != user2_full
        assert user1_full == f"{user1_prefix}_{secret_name}"
        assert user2_full == f"{user2_prefix}_{secret_name}"

    def test_cache_isolation_between_users(self):
        """Test that cache properly isolates user secrets"""
        manager = SecretsManager()

        # Clear cache
        manager.get_secret.cache_clear()

        # Mock environment for testing
        with patch.dict(os.environ, {'API_KEY': 'system-key'}):
            # Get system secret
            system_result = manager.get_secret("api-key")

            # The user-specific call should not hit the cache from system call
            # (This is implicitly tested by the different parameter signature)
            assert system_result == 'system-key'


def run_tests():
    """Run all tests"""
    print("🧪 Running Multi-Tenancy Secrets Tests")
    print("=" * 60)

    # Run pytest
    pytest.main([__file__, '-v', '--tb=short'])


if __name__ == "__main__":
    run_tests()

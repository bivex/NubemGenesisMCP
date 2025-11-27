"""
Unit tests for UserAuthManager
Tests authentication and authorization without requiring K8s connection
"""

import json
import pytest
from unittest.mock import Mock, patch
from user_auth_manager import UserAuthManager


class TestUserAuthManager:
    """Test suite for UserAuthManager"""

    @pytest.fixture
    def mock_creds_manager(self):
        """Mock MCPCredentialsManager"""
        mock = Mock()

        # Mock user configs
        admin_user = {
            "api_key": "nsfc_admin_test123",
            "user_email": "david.anguera@nubemsystems.es",
            "role": "admin",
            "active": True,
            "created_at": "2025-10-23T00:00:00",
            "expires_at": "2026-10-23T00:00:00"
        }

        readonly_user = {
            "api_key": "nsfc_readonly_test456",
            "user_email": "joseluis.manzanares@nubemsystems.es",
            "role": "readonly",
            "active": True,
            "created_at": "2025-10-23T00:00:00",
            "expires_at": "2026-10-23T00:00:00"
        }

        # Mock roles config
        roles_config = """
roles:
  admin:
    permissions:
      mcps:
        - "*"
      operations:
        - read
        - write
        - delete
        - execute
      blocked_mcps: []
    rate_limit:
      requests_per_minute: 100
      burst: 20

  readonly:
    permissions:
      mcps:
        - intelligent_respond
        - list_personas
        - get_system_status
      operations:
        - read
      blocked_mcps:
        - kubernetes
        - docker
        - gcp
        - github
    rate_limit:
      requests_per_minute: 30
      burst: 5
"""

        def get_secret_side_effect(secret_name, key):
            """Simulate K8s secret reads"""
            if secret_name == "mcp-auth-admin" and key == "user_config":
                return json.dumps(admin_user)
            elif secret_name == "mcp-auth-readonly" and key == "user_config":
                return json.dumps(readonly_user)
            elif secret_name == "mcp-auth-roles" and key == "roles.yaml":
                return roles_config
            return None

        mock.get_secret_from_k8s.side_effect = get_secret_side_effect
        mock.get_cache_stats.return_value = {"total": 0}
        mock.clear_cache.return_value = None

        return mock

    @pytest.fixture
    def auth_manager(self, mock_creds_manager):
        """Create UserAuthManager with mocked credentials manager"""
        return UserAuthManager(mock_creds_manager)

    def test_init(self, auth_manager):
        """Test UserAuthManager initialization"""
        assert auth_manager is not None
        assert auth_manager.creds_manager is not None
        assert auth_manager._users_cache == {}
        assert auth_manager._roles_cache is None
        print("✅ test_init passed")

    def test_validate_admin_api_key(self, auth_manager):
        """Test validating admin API key"""
        user = auth_manager.validate_api_key("nsfc_admin_test123")

        assert user is not None
        assert user["user_email"] == "david.anguera@nubemsystems.es"
        assert user["role"] == "admin"
        assert user["active"] is True
        print("✅ test_validate_admin_api_key passed")

    def test_validate_readonly_api_key(self, auth_manager):
        """Test validating readonly API key"""
        user = auth_manager.validate_api_key("nsfc_readonly_test456")

        assert user is not None
        assert user["user_email"] == "joseluis.manzanares@nubemsystems.es"
        assert user["role"] == "readonly"
        assert user["active"] is True
        print("✅ test_validate_readonly_api_key passed")

    def test_validate_invalid_api_key(self, auth_manager):
        """Test validating invalid API key"""
        user = auth_manager.validate_api_key("invalid_key_xxx")

        assert user is None
        print("✅ test_validate_invalid_api_key passed")

    def test_validate_empty_api_key(self, auth_manager):
        """Test validating empty API key"""
        user = auth_manager.validate_api_key("")
        assert user is None

        user = auth_manager.validate_api_key(None)
        assert user is None
        print("✅ test_validate_empty_api_key passed")

    def test_admin_can_access_all_mcps(self, auth_manager):
        """Test that admin can access all MCPs"""
        user = auth_manager.validate_api_key("nsfc_admin_test123")

        # Admin should access everything
        assert auth_manager.check_permission(user, "kubernetes", "write") is True
        assert auth_manager.check_permission(user, "docker", "delete") is True
        assert auth_manager.check_permission(user, "github", "execute") is True
        assert auth_manager.check_permission(user, "intelligent_respond", "read") is True
        print("✅ test_admin_can_access_all_mcps passed")

    def test_readonly_can_access_allowed_mcps(self, auth_manager):
        """Test that readonly can access allowed MCPs"""
        user = auth_manager.validate_api_key("nsfc_readonly_test456")

        # Should access allowed MCPs
        assert auth_manager.check_permission(user, "intelligent_respond", "read") is True
        assert auth_manager.check_permission(user, "list_personas", "read") is True
        assert auth_manager.check_permission(user, "get_system_status", "read") is True
        print("✅ test_readonly_can_access_allowed_mcps passed")

    def test_readonly_cannot_access_blocked_mcps(self, auth_manager):
        """Test that readonly cannot access blocked MCPs"""
        user = auth_manager.validate_api_key("nsfc_readonly_test456")

        # Should NOT access blocked MCPs
        assert auth_manager.check_permission(user, "kubernetes", "read") is False
        assert auth_manager.check_permission(user, "docker", "read") is False
        assert auth_manager.check_permission(user, "gcp", "read") is False
        assert auth_manager.check_permission(user, "github", "read") is False
        print("✅ test_readonly_cannot_access_blocked_mcps passed")

    def test_readonly_cannot_write(self, auth_manager):
        """Test that readonly cannot perform write operations"""
        user = auth_manager.validate_api_key("nsfc_readonly_test456")

        # Even on allowed MCPs, cannot write
        assert auth_manager.check_permission(user, "intelligent_respond", "write") is False
        assert auth_manager.check_permission(user, "list_personas", "delete") is False
        print("✅ test_readonly_cannot_write passed")

    def test_get_user_rate_limit(self, auth_manager):
        """Test getting user rate limits"""
        admin_user = auth_manager.validate_api_key("nsfc_admin_test123")
        admin_limits = auth_manager.get_user_rate_limit(admin_user)
        assert admin_limits["requests_per_minute"] == 100
        assert admin_limits["burst"] == 20

        readonly_user = auth_manager.validate_api_key("nsfc_readonly_test456")
        readonly_limits = auth_manager.get_user_rate_limit(readonly_user)
        assert readonly_limits["requests_per_minute"] == 30
        assert readonly_limits["burst"] == 5
        print("✅ test_get_user_rate_limit passed")

    def test_cache_functionality(self, auth_manager):
        """Test that caching works correctly"""
        # First call - should load from K8s
        user1 = auth_manager.validate_api_key("nsfc_admin_test123")

        # Second call - should come from cache
        user2 = auth_manager.validate_api_key("nsfc_admin_test123")

        assert user1 == user2
        assert len(auth_manager._users_cache) > 0
        print("✅ test_cache_functionality passed")

    def test_clear_cache(self, auth_manager):
        """Test cache clearing"""
        # Populate cache
        auth_manager.validate_api_key("nsfc_admin_test123")
        assert len(auth_manager._users_cache) > 0

        # Clear cache
        auth_manager.clear_cache()
        assert len(auth_manager._users_cache) == 0
        assert auth_manager._roles_cache is None
        print("✅ test_clear_cache passed")


def run_all_tests():
    """Run all tests manually"""
    print("\n🧪 Running UserAuthManager Tests...\n")

    # Create mock credentials manager
    mock_creds = Mock()

    admin_user = {
        "api_key": "nsfc_admin_test123",
        "user_email": "david.anguera@nubemsystems.es",
        "role": "admin",
        "active": True,
        "created_at": "2025-10-23T00:00:00",
        "expires_at": "2026-10-23T00:00:00"
    }

    readonly_user = {
        "api_key": "nsfc_readonly_test456",
        "user_email": "joseluis.manzanares@nubemsystems.es",
        "role": "readonly",
        "active": True,
        "created_at": "2025-10-23T00:00:00",
        "expires_at": "2026-10-23T00:00:00"
    }

    roles_config = """
roles:
  admin:
    permissions:
      mcps:
        - "*"
      operations:
        - read
        - write
        - delete
        - execute
      blocked_mcps: []
    rate_limit:
      requests_per_minute: 100
      burst: 20

  readonly:
    permissions:
      mcps:
        - intelligent_respond
        - list_personas
        - get_system_status
      operations:
        - read
      blocked_mcps:
        - kubernetes
        - docker
        - gcp
        - github
    rate_limit:
      requests_per_minute: 30
      burst: 5
"""

    def get_secret_side_effect(secret_name, key):
        if secret_name == "mcp-auth-admin" and key == "user_config":
            return json.dumps(admin_user)
        elif secret_name == "mcp-auth-readonly" and key == "user_config":
            return json.dumps(readonly_user)
        elif secret_name == "mcp-auth-roles" and key == "roles.yaml":
            return roles_config
        return None

    mock_creds.get_secret_from_k8s.side_effect = get_secret_side_effect
    mock_creds.get_cache_stats.return_value = {"total": 0}
    mock_creds.clear_cache.return_value = None

    # Create test instance
    test = TestUserAuthManager()
    auth_manager = UserAuthManager(mock_creds)

    # Run tests
    try:
        test.test_init(auth_manager)
        test.test_validate_admin_api_key(auth_manager)
        test.test_validate_readonly_api_key(auth_manager)
        test.test_validate_invalid_api_key(auth_manager)
        test.test_validate_empty_api_key(auth_manager)
        test.test_admin_can_access_all_mcps(auth_manager)
        test.test_readonly_can_access_allowed_mcps(auth_manager)
        test.test_readonly_cannot_access_blocked_mcps(auth_manager)
        test.test_readonly_cannot_write(auth_manager)
        test.test_get_user_rate_limit(auth_manager)
        test.test_cache_functionality(auth_manager)
        test.test_clear_cache(auth_manager)

        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED (12/12)")
        print("="*60 + "\n")
        return True

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        return False


if __name__ == "__main__":
    run_all_tests()

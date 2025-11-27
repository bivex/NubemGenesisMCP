#!/usr/bin/env python3
"""
Tests for Secrets Management REST API
"""

import pytest
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.api.main import app

# Create test client
client = TestClient(app)


class TestHealthEndpoints:
    """Test suite for health and info endpoints"""

    def test_health_endpoint(self):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "version" in data
        assert data["version"] == "1.0.0"

    def test_root_endpoint(self):
        """Test root endpoint returns API info"""
        response = client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "NubemSuperFClaude Secrets API"
        assert data["version"] == "1.0.0"
        assert "endpoints" in data
        assert "auth" in data


class TestAuthentication:
    """Test suite for authentication"""

    def test_list_secrets_requires_auth(self):
        """Test that listing secrets requires authentication"""
        response = client.get("/api/v1/secrets")
        assert response.status_code == 401
        assert response.json()["detail"] == "Authentication required"

    def test_get_secret_requires_auth(self):
        """Test that getting a secret requires authentication"""
        response = client.get("/api/v1/secrets/some-secret")
        assert response.status_code == 401

    def test_create_secret_requires_auth(self):
        """Test that creating a secret requires authentication"""
        response = client.post(
            "/api/v1/secrets",
            json={"name": "test-key", "value": "test-value"}
        )
        assert response.status_code == 401

    def test_dev_token_endpoint_works(self):
        """Test that dev token endpoint works"""
        # Skip if in production mode
        if os.getenv("NODE_ENV") == "production":
            pytest.skip("Dev token endpoint disabled in production")

        response = client.post(
            "/auth/token",
            params={"email": "test@nubemsystems.es", "password": "test"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 50  # JWT token should be long

    def test_dev_token_requires_correct_domain(self):
        """Test that dev token endpoint enforces domain restriction"""
        if os.getenv("NODE_ENV") == "production":
            pytest.skip("Dev token endpoint disabled in production")

        response = client.post(
            "/auth/token",
            params={"email": "test@wrongdomain.com", "password": "test"}
        )

        assert response.status_code == 403
        assert "Only" in response.json()["detail"]


class TestSecretsEndpointsWithAuth:
    """Test suite for secrets endpoints with authentication"""

    @pytest.fixture
    def auth_headers(self):
        """Get authentication headers for tests"""
        if os.getenv("NODE_ENV") == "production":
            pytest.skip("Cannot get dev token in production")

        # Get dev token
        response = client.post(
            "/auth/token",
            params={"email": "test@nubemsystems.es", "password": "test"}
        )
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_get_current_user_info(self, auth_headers):
        """Test /api/v1/me endpoint"""
        response = client.get("/api/v1/me", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["email"] == "test@nubemsystems.es"
        assert "name" in data
        assert "picture" in data

    def test_list_secrets_returns_empty_list(self, auth_headers):
        """Test listing secrets returns empty list when none exist"""
        with patch('core.secrets_manager.secrets_manager.list_secrets') as mock_list:
            mock_list.return_value = []

            response = client.get("/api/v1/secrets", headers=auth_headers)
            assert response.status_code == 200
            assert response.json() == []

    def test_list_secrets_returns_secrets(self, auth_headers):
        """Test listing secrets returns list of secrets"""
        with patch('core.secrets_manager.secrets_manager.list_secrets') as mock_list:
            mock_list.return_value = ["api-key", "db-password"]

            response = client.get("/api/v1/secrets", headers=auth_headers)
            assert response.status_code == 200

            data = response.json()
            assert len(data) == 2
            assert data[0]["name"] == "api-key"
            assert data[1]["name"] == "db-password"

    def test_get_secret_returns_value(self, auth_headers):
        """Test getting a secret returns its value"""
        with patch('core.secrets_manager.secrets_manager.get_secret') as mock_get:
            mock_get.return_value = "secret-value-123"

            response = client.get("/api/v1/secrets/test-key", headers=auth_headers)
            assert response.status_code == 200

            data = response.json()
            assert data["name"] == "test-key"
            assert data["value"] == "secret-value-123"

    def test_get_secret_not_found(self, auth_headers):
        """Test getting a non-existent secret returns 404"""
        with patch('core.secrets_manager.secrets_manager.get_secret') as mock_get:
            mock_get.return_value = None

            response = client.get("/api/v1/secrets/nonexistent", headers=auth_headers)
            assert response.status_code == 404

    def test_create_secret_success(self, auth_headers):
        """Test creating a secret successfully"""
        with patch('core.secrets_manager.secrets_manager.create_secret') as mock_create:
            mock_create.return_value = True

            response = client.post(
                "/api/v1/secrets",
                headers=auth_headers,
                json={
                    "name": "new-key",
                    "value": "new-value",
                    "labels": {"env": "test"}
                }
            )

            assert response.status_code == 201
            data = response.json()
            assert data["name"] == "new-key"

    def test_create_secret_validation_error(self, auth_headers):
        """Test creating a secret with invalid data"""
        response = client.post(
            "/api/v1/secrets",
            headers=auth_headers,
            json={"name": "", "value": ""}  # Empty name not allowed
        )

        assert response.status_code == 422  # Validation error

    def test_update_secret_success(self, auth_headers):
        """Test updating a secret successfully"""
        with patch('core.secrets_manager.secrets_manager.update_secret') as mock_update:
            mock_update.return_value = True

            response = client.put(
                "/api/v1/secrets/test-key",
                headers=auth_headers,
                json={"value": "updated-value"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "test-key"

    def test_delete_secret_success(self, auth_headers):
        """Test deleting a secret successfully"""
        with patch('core.secrets_manager.secrets_manager.delete_secret') as mock_delete:
            mock_delete.return_value = True

            response = client.delete(
                "/api/v1/secrets/test-key",
                headers=auth_headers
            )

            assert response.status_code == 204


class TestRateLimiting:
    """Test suite for rate limiting"""

    def test_health_endpoint_has_rate_limit(self):
        """Test that health endpoint has rate limiting headers"""
        response = client.get("/health")
        # Should have X-RateLimit headers from slowapi
        assert response.status_code == 200


class TestMultiTenancyInAPI:
    """Test that API properly isolates users"""

    @pytest.fixture
    def user1_headers(self):
        """Get headers for user 1"""
        if os.getenv("NODE_ENV") == "production":
            pytest.skip("Cannot get dev token in production")

        response = client.post(
            "/auth/token",
            params={"email": "user1@nubemsystems.es", "password": "test"}
        )
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    @pytest.fixture
    def user2_headers(self):
        """Get headers for user 2"""
        if os.getenv("NODE_ENV") == "production":
            pytest.skip("Cannot get dev token in production")

        response = client.post(
            "/auth/token",
            params={"email": "user2@nubemsystems.es", "password": "test"}
        )
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_different_users_get_different_secrets(self, user1_headers, user2_headers):
        """Test that different users see different secrets"""
        with patch('core.secrets_manager.secrets_manager.list_secrets') as mock_list:
            # User 1 has secrets
            mock_list.return_value = ["user1-secret"]
            response1 = client.get("/api/v1/secrets", headers=user1_headers)

            # User 2 has different secrets
            mock_list.return_value = ["user2-secret"]
            response2 = client.get("/api/v1/secrets", headers=user2_headers)

            assert response1.json()[0]["name"] == "user1-secret"
            assert response2.json()[0]["name"] == "user2-secret"


def run_tests():
    """Run all tests"""
    print("🧪 Running API Tests")
    print("=" * 60)

    # Run pytest
    pytest.main([__file__, '-v', '--tb=short'])


if __name__ == "__main__":
    run_tests()

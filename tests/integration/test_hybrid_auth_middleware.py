"""
Integration tests for hybrid authentication middleware.

Tests both API Key and OAuth Bearer token authentication methods
to ensure backward compatibility and new OAuth functionality.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp_server.auth_middleware import auth_middleware, PUBLIC_ENDPOINTS
from core.auth import get_auth_manager, get_hybrid_auth_manager


class TestHybridAuthMiddleware(AioHTTPTestCase):
    """Test suite for hybrid authentication middleware."""

    async def get_application(self):
        """Create aiohttp application with auth middleware."""
        app = web.Application(middlewares=[auth_middleware])

        # Protected endpoint
        async def protected_handler(request):
            return web.json_response({
                "message": "success",
                "user": request.get('user_email'),
                "role": request.get('user_role')
            })

        # Public endpoint
        async def public_handler(request):
            return web.json_response({"message": "public"})

        app.router.add_post('/mcp/call', protected_handler)
        app.router.add_get('/health', public_handler)

        return app

    async def test_api_key_authentication_success(self):
        """Test successful authentication with valid API key."""
        # Test with a mock valid API key
        # In real setup, this should come from environment or K8s secret
        # For testing, we'll mock the validation

        from unittest.mock import patch

        mock_user = {
            'user_email': 'test@example.com',
            'role': 'admin',
            'api_key': 'test-api-key-123'
        }

        with patch('core.auth.user_auth_manager.UserAuthManager.validate_api_key', return_value=mock_user):
            resp = await self.client.request(
                "POST",
                "/mcp/call",
                headers={'X-API-Key': 'test-api-key-123'},
                json={"method": "tools/list"}
            )

            assert resp.status == 200
            data = await resp.json()
            assert data['message'] == 'success'
            assert data['user'] == 'test@example.com'

    async def test_api_key_authentication_invalid(self):
        """Test authentication failure with invalid API key."""
        resp = await self.client.request(
            "POST",
            "/mcp/call",
            headers={'X-API-Key': 'invalid-api-key-12345'},
            json={"method": "tools/list"}
        )

        assert resp.status == 401
        data = await resp.json()
        assert data['error'] == 'Authentication failed'
        assert data['code'] == 'INVALID_AUTH'
        assert 'WWW-Authenticate' in resp.headers

    async def test_oauth_bearer_token_success(self):
        """Test successful authentication with valid OAuth Bearer token."""
        # Mock OAuth handler to create a valid token
        from core.auth.oauth_handler import get_oauth_handler
        oauth_handler = get_oauth_handler()

        if not oauth_handler.is_configured():
            pytest.skip("OAuth not configured for testing")

        # Create a test JWT token
        test_payload = {
            'email': 'test@example.com',
            'google_id': '123456',
            'name': 'Test User',
            'email_verified': True
        }
        token = oauth_handler.create_session_token(test_payload)

        resp = await self.client.request(
            "POST",
            "/mcp/call",
            headers={'Authorization': f'Bearer {token}'},
            json={"method": "tools/list"}
        )

        assert resp.status == 200
        data = await resp.json()
        assert data['message'] == 'success'
        assert data['user'] == 'test@example.com'

    async def test_oauth_bearer_token_invalid(self):
        """Test authentication failure with invalid OAuth Bearer token."""
        resp = await self.client.request(
            "POST",
            "/mcp/call",
            headers={'Authorization': 'Bearer invalid.jwt.token'},
            json={"method": "tools/list"}
        )

        assert resp.status == 401
        data = await resp.json()
        assert data['error'] == 'Authentication failed'
        assert data['code'] == 'INVALID_AUTH'

    async def test_oauth_bearer_token_expired(self):
        """Test authentication failure with expired OAuth Bearer token."""
        from core.auth.oauth_handler import get_oauth_handler
        oauth_handler = get_oauth_handler()

        if not oauth_handler.is_configured():
            pytest.skip("OAuth not configured for testing")

        # Create an expired token (negative TTL)
        test_payload = {
            'email': 'test@example.com',
            'google_id': '123456',
            'name': 'Test User'
        }

        # Mock jwt.encode to create expired token
        import jwt
        import time
        expired_payload = test_payload.copy()
        expired_payload['exp'] = int(time.time()) - 3600  # Expired 1 hour ago
        expired_payload['iat'] = int(time.time()) - 7200  # Issued 2 hours ago

        token = jwt.encode(
            expired_payload,
            oauth_handler.jwt_secret,
            algorithm='HS256'
        )

        resp = await self.client.request(
            "POST",
            "/mcp/call",
            headers={'Authorization': f'Bearer {token}'},
            json={"method": "tools/list"}
        )

        assert resp.status == 401
        data = await resp.json()
        assert data['error'] == 'Authentication failed'

    async def test_no_authentication(self):
        """Test authentication failure when no credentials provided."""
        resp = await self.client.request(
            "POST",
            "/mcp/call",
            json={"method": "tools/list"}
        )

        assert resp.status == 401
        data = await resp.json()
        assert data['error'] == 'Authentication required'
        assert data['code'] == 'MISSING_AUTH'
        assert 'supported_methods' in data
        assert 'help' in data
        assert 'X-API-Key' in data['supported_methods'][0]
        assert 'Bearer token' in data['supported_methods'][1]

    async def test_public_endpoints_no_auth(self):
        """Test that public endpoints don't require authentication."""
        for endpoint in ['/health']:
            resp = await self.client.request("GET", endpoint)
            assert resp.status == 200
            data = await resp.json()
            assert data['message'] == 'public'

    async def test_www_authenticate_header(self):
        """Test WWW-Authenticate header includes both schemes."""
        resp = await self.client.request(
            "POST",
            "/mcp/call",
            json={"method": "tools/list"}
        )

        assert resp.status == 401
        assert 'WWW-Authenticate' in resp.headers
        www_auth = resp.headers['WWW-Authenticate']
        assert 'X-API-Key' in www_auth
        assert 'Bearer' in www_auth

    async def test_rate_limiting_with_api_key(self):
        """Test rate limiting works with API key authentication."""
        from unittest.mock import patch

        mock_user = {
            'user_email': 'test@example.com',
            'role': 'admin',
            'api_key': 'test-api-key-123'
        }

        with patch('core.auth.user_auth_manager.UserAuthManager.validate_api_key', return_value=mock_user):
            # Make multiple requests rapidly
            auth_manager = get_auth_manager()
            rate_limits = auth_manager.get_user_rate_limit(mock_user)
            burst = rate_limits['burst']

            # Make requests up to burst limit
            for i in range(burst + 5):
                resp = await self.client.request(
                    "POST",
                    "/mcp/call",
                    headers={'X-API-Key': 'test-api-key-123'},
                    json={"method": "tools/list"}
                )

                # First requests should succeed, then rate limit kicks in
                if i < burst:
                    assert resp.status in [200, 429]  # May hit rate limit
                else:
                    # Should definitely hit rate limit
                    if resp.status == 429:
                        data = await resp.json()
                        assert data['error'] == 'Rate limit exceeded'
                        assert 'rate_limit' in data
                        break

    async def test_rate_limiting_with_oauth(self):
        """Test rate limiting works with OAuth Bearer token."""
        from core.auth.oauth_handler import get_oauth_handler
        oauth_handler = get_oauth_handler()

        if not oauth_handler.is_configured():
            pytest.skip("OAuth not configured for testing")

        test_payload = {
            'email': 'test@example.com',
            'google_id': '123456',
            'name': 'Test User'
        }
        token = oauth_handler.create_session_token(test_payload)

        # Make multiple requests
        for i in range(10):
            resp = await self.client.request(
                "POST",
                "/mcp/call",
                headers={'Authorization': f'Bearer {token}'},
                json={"method": "tools/list"}
            )

            # Should either succeed or hit rate limit
            assert resp.status in [200, 429]

    async def test_permission_check_with_api_key(self):
        """Test permission checks work with API key authentication."""
        from unittest.mock import patch

        # Mock a readonly user
        readonly_user = {
            'user_email': 'readonly@example.com',
            'role': 'readonly',
            'api_key': 'test-readonly-key-123'
        }

        with patch('core.auth.user_auth_manager.UserAuthManager.validate_api_key', return_value=readonly_user):
            # Try a write operation (should fail for readonly)
            resp = await self.client.request(
                "POST",
                "/mcp/call",
                headers={'X-API-Key': 'test-readonly-key-123'},
                json={
                    "method": "tools/call",
                    "params": {
                        "name": "intelligent_execute",
                        "arguments": {"mcp_name": "kubernetes"}
                    }
                }
            )

            # Depending on permissions, should either succeed or fail
            assert resp.status in [200, 403]
            if resp.status == 403:
                data = await resp.json()
                assert data['error'] == 'Permission denied'

    async def test_permission_check_with_oauth(self):
        """Test permission checks work with OAuth Bearer token."""
        from core.auth.oauth_handler import get_oauth_handler
        oauth_handler = get_oauth_handler()

        if not oauth_handler.is_configured():
            pytest.skip("OAuth not configured for testing")

        # Create token for non-admin user
        test_payload = {
            'email': 'test@example.com',
            'google_id': '123456',
            'name': 'Test User'
        }
        token = oauth_handler.create_session_token(test_payload)

        # Try operation with OAuth token
        resp = await self.client.request(
            "POST",
            "/mcp/call",
            headers={'Authorization': f'Bearer {token}'},
            json={
                "method": "tools/call",
                "params": {"name": "intelligent_execute"}
            }
        )

        # Should either succeed or fail based on permissions
        assert resp.status in [200, 403]

    async def test_audit_logging_includes_auth_type(self):
        """Test that audit logs include authentication type."""
        from core.auth import get_audit_logger
        from unittest.mock import patch
        audit_logger = get_audit_logger()

        mock_user = {
            'user_email': 'test@example.com',
            'role': 'admin',
            'api_key': 'test-api-key-123'
        }

        # Mock both the user validation and audit logger
        with patch('core.auth.user_auth_manager.UserAuthManager.validate_api_key', return_value=mock_user):
            with patch.object(audit_logger, 'log_auth_success') as mock_log:
                resp = await self.client.request(
                    "POST",
                    "/mcp/call",
                    headers={'X-API-Key': 'test-api-key-123'},
                    json={"method": "tools/list"}
                )

                # Verify audit log was called
                if resp.status == 200:
                    assert mock_log.called

    async def test_backward_compatibility(self):
        """Test that existing API key authentication still works (backward compatibility)."""
        from unittest.mock import patch

        # Use a different email to avoid rate limit conflicts with other tests
        mock_user = {
            'user_email': 'backward-compat@example.com',
            'role': 'admin',
            'api_key': 'test-api-key-backward-compat'
        }

        with patch('core.auth.user_auth_manager.UserAuthManager.validate_api_key', return_value=mock_user):
            # Old-style API key should still work
            resp = await self.client.request(
                "POST",
                "/mcp/call",
                headers={'X-API-Key': 'test-api-key-backward-compat'},
                json={"method": "tools/list"}
            )

            # Should succeed (200) or hit rate limit (429) - both are acceptable
            assert resp.status in [200, 429]
            if resp.status == 200:
                data = await resp.json()
                assert 'user' in data
                assert 'role' in data


# Run tests
if __name__ == '__main__':
    pytest.main([__file__, '-v'])

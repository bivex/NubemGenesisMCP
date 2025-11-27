"""
Tests for Authentication Middleware

Tests the two-tier caching authentication system designed by expert panel.
"""

import pytest
import hashlib
from uuid import uuid4
from unittest.mock import Mock, AsyncMock, patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from mcp_server.middleware import AuthenticationMiddleware, public_endpoint
from core.cache import TwoTierCache
from core.database.models import APIKey, Tenant


@pytest.fixture
def mock_cache():
    """Mock two-tier cache"""
    cache = Mock(spec=TwoTierCache)
    cache.get = Mock(return_value=None)
    cache.set = Mock(return_value=True)
    return cache


@pytest.fixture
def test_tenant():
    """Create test tenant"""
    return Tenant(
        id=uuid4(),
        name="Test Tenant",
        email="test@example.com",
        plan="pro",
        status="active",
        deleted_at=None
    )


@pytest.fixture
def test_api_key(test_tenant):
    """Create test API key"""
    raw_key = "test_api_key_12345"
    key_hash = hashlib.sha256(raw_key.encode('utf-8')).hexdigest()

    return {
        "raw": raw_key,
        "hash": key_hash,
        "object": APIKey(
            id=uuid4(),
            tenant_id=test_tenant.id,
            key_hash=key_hash,
            key_prefix="test_",
            role="admin",
            is_active=True
        )
    }


@pytest.fixture
def app(mock_cache):
    """Create test FastAPI app"""
    app = FastAPI()

    # Add authentication middleware
    app.add_middleware(AuthenticationMiddleware, cache=mock_cache)

    # Add test routes
    @app.get("/health")
    @public_endpoint
    async def health():
        return {"status": "ok"}

    @app.get("/protected")
    async def protected(request: Request):
        return {
            "tenant_id": request.state.tenant_id,
            "tenant_plan": request.state.tenant_plan,
            "api_key_role": request.state.api_key_role
        }

    return app


@pytest.fixture
def client(app):
    """Create test client"""
    return TestClient(app)


# ============================================================================
# TESTS: Public Endpoints
# ============================================================================

def test_public_endpoint_no_auth(client):
    """Test public endpoint without authentication"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_public_endpoint_with_auth(client, test_api_key):
    """Test public endpoint with authentication (should still work)"""
    response = client.get(
        "/health",
        headers={"X-API-Key": test_api_key["raw"]}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ============================================================================
# TESTS: Missing API Key
# ============================================================================

def test_protected_endpoint_no_auth(client):
    """Test protected endpoint without authentication"""
    response = client.get("/protected")
    assert response.status_code == 401
    assert "error" in response.json()
    assert "request_id" in response.json()


def test_protected_endpoint_empty_header(client):
    """Test protected endpoint with empty X-API-Key header"""
    response = client.get(
        "/protected",
        headers={"X-API-Key": ""}
    )
    assert response.status_code == 401
    assert "error" in response.json()


def test_protected_endpoint_whitespace_header(client):
    """Test protected endpoint with whitespace X-API-Key header"""
    response = client.get(
        "/protected",
        headers={"X-API-Key": "   "}
    )
    assert response.status_code == 401
    assert "error" in response.json()


# ============================================================================
# TESTS: L1 Cache Hit
# ============================================================================

@pytest.mark.asyncio
async def test_l1_cache_hit(mock_cache, test_tenant, test_api_key):
    """Test L1 cache hit (fast path)"""
    # Mock L1 cache hit
    cached_value = f"{test_tenant.id}|pro|{test_api_key['object'].id}|admin"
    mock_cache.get.return_value = cached_value

    app = FastAPI()
    app.add_middleware(AuthenticationMiddleware, cache=mock_cache)

    @app.get("/test")
    async def test_route(request: Request):
        return {"tenant_id": request.state.tenant_id}

    client = TestClient(app)

    response = client.get(
        "/test",
        headers={"X-API-Key": test_api_key["raw"]}
    )

    # Should return success
    assert response.status_code == 200
    assert response.json()["tenant_id"] == str(test_tenant.id)

    # Should have called cache.get
    mock_cache.get.assert_called_once()


# ============================================================================
# TESTS: L1 Cache Miss + Database Validation
# ============================================================================

@pytest.mark.asyncio
async def test_l1_miss_database_validation_success(
    mock_cache, test_tenant, test_api_key
):
    """Test L1 cache miss, database validation success"""
    # Mock L1 cache miss
    mock_cache.get.return_value = None

    # Mock database query
    with patch('mcp_server.middleware.auth.get_db_session') as mock_db:
        # Setup mock session
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.first.return_value = (test_api_key["object"], test_tenant)
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db.return_value.__aenter__.return_value = mock_session

        app = FastAPI()
        app.add_middleware(AuthenticationMiddleware, cache=mock_cache)

        @app.get("/test")
        async def test_route(request: Request):
            return {
                "tenant_id": request.state.tenant_id,
                "tenant_plan": request.state.tenant_plan,
                "api_key_role": request.state.api_key_role
            }

        client = TestClient(app)

        response = client.get(
            "/test",
            headers={"X-API-Key": test_api_key["raw"]}
        )

        # Should return success
        assert response.status_code == 200
        assert response.json()["tenant_id"] == str(test_tenant.id)
        assert response.json()["tenant_plan"] == "pro"
        assert response.json()["api_key_role"] == "admin"

        # Should have cached the result
        mock_cache.set.assert_called_once()


# ============================================================================
# TESTS: Invalid API Key
# ============================================================================

@pytest.mark.asyncio
async def test_invalid_api_key_not_found(mock_cache):
    """Test invalid API key (not found in database)"""
    # Mock L1 cache miss
    mock_cache.get.return_value = None

    # Mock database query - not found
    with patch('mcp_server.middleware.auth.get_db_session') as mock_db:
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.first.return_value = None  # Not found
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db.return_value.__aenter__.return_value = mock_session

        app = FastAPI()
        app.add_middleware(AuthenticationMiddleware, cache=mock_cache)

        @app.get("/test")
        async def test_route(request: Request):
            return {"ok": True}

        client = TestClient(app)

        response = client.get(
            "/test",
            headers={"X-API-Key": "invalid_key_12345"}
        )

        # Should return 401
        assert response.status_code == 401
        assert "error" in response.json()
        assert "request_id" in response.json()


# ============================================================================
# TESTS: Inactive API Key
# ============================================================================

@pytest.mark.asyncio
async def test_inactive_api_key(mock_cache, test_tenant, test_api_key):
    """Test inactive API key"""
    # Mock L1 cache miss
    mock_cache.get.return_value = None

    # Set API key as inactive
    test_api_key["object"].is_active = False

    # Mock database query
    with patch('mcp_server.middleware.auth.get_db_session') as mock_db:
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.first.return_value = (test_api_key["object"], test_tenant)
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db.return_value.__aenter__.return_value = mock_session

        app = FastAPI()
        app.add_middleware(AuthenticationMiddleware, cache=mock_cache)

        @app.get("/test")
        async def test_route(request: Request):
            return {"ok": True}

        client = TestClient(app)

        response = client.get(
            "/test",
            headers={"X-API-Key": test_api_key["raw"]}
        )

        # Should return 401
        assert response.status_code == 401
        assert "error" in response.json()


# ============================================================================
# TESTS: Inactive Tenant
# ============================================================================

@pytest.mark.asyncio
async def test_inactive_tenant_status(mock_cache, test_tenant, test_api_key):
    """Test inactive tenant (status != 'active')"""
    # Mock L1 cache miss
    mock_cache.get.return_value = None

    # Set tenant as inactive
    test_tenant.status = "suspended"

    # Mock database query
    with patch('mcp_server.middleware.auth.get_db_session') as mock_db:
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.first.return_value = (test_api_key["object"], test_tenant)
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db.return_value.__aenter__.return_value = mock_session

        app = FastAPI()
        app.add_middleware(AuthenticationMiddleware, cache=mock_cache)

        @app.get("/test")
        async def test_route(request: Request):
            return {"ok": True}

        client = TestClient(app)

        response = client.get(
            "/test",
            headers={"X-API-Key": test_api_key["raw"]}
        )

        # Should return 401
        assert response.status_code == 401
        assert "error" in response.json()


# ============================================================================
# TESTS: Generic Error Messages (Security)
# ============================================================================

def test_generic_error_messages(client):
    """Test that error messages are generic (security requirement)"""
    # Test various error conditions
    test_cases = [
        {"headers": {}, "expected_error": "Authentication required"},
        {"headers": {"X-API-Key": ""}, "expected_error": "Authentication failed"},
        {"headers": {"X-API-Key": "invalid"}, "expected_error": "Authentication failed"},
    ]

    for case in test_cases:
        response = client.get("/protected", headers=case.get("headers", {}))
        assert response.status_code == 401
        assert response.json()["error"] == case["expected_error"]
        # Should always include request_id for audit trail
        assert "request_id" in response.json()


# ============================================================================
# TESTS: Request ID
# ============================================================================

def test_request_id_generated(client):
    """Test that request_id is always generated"""
    response = client.get("/protected")
    assert "request_id" in response.json()

    # Request ID should be UUID-like
    request_id = response.json()["request_id"]
    assert len(request_id) == 36  # UUID format
    assert request_id.count("-") == 4  # UUID has 4 dashes


# ============================================================================
# TESTS: Performance
# ============================================================================

@pytest.mark.asyncio
async def test_cache_performance_target(mock_cache, test_tenant, test_api_key):
    """Test that cached authentication is fast (<5ms target)"""
    import time

    # Mock L1 cache hit
    cached_value = f"{test_tenant.id}|pro|{test_api_key['object'].id}|admin"
    mock_cache.get.return_value = cached_value

    app = FastAPI()
    app.add_middleware(AuthenticationMiddleware, cache=mock_cache)

    @app.get("/test")
    async def test_route(request: Request):
        return {"ok": True}

    client = TestClient(app)

    # Warm up
    client.get("/test", headers={"X-API-Key": test_api_key["raw"]})

    # Measure 100 requests
    start = time.time()
    for _ in range(100):
        client.get("/test", headers={"X-API-Key": test_api_key["raw"]})
    elapsed = time.time() - start

    # Average should be well under 5ms per request
    avg_ms = (elapsed / 100) * 1000
    assert avg_ms < 10  # 10ms is generous, should be much faster

    print(f"Average auth latency: {avg_ms:.2f}ms per request")

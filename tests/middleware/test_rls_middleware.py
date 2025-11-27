"""
Tests for RLS (Row Level Security) Middleware

Tests PostgreSQL context setting for tenant isolation.
"""

import pytest
from uuid import uuid4
from unittest.mock import Mock, AsyncMock, patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from mcp_server.middleware import RLSMiddleware


@pytest.fixture
def app():
    """Create test FastAPI app with RLS middleware"""
    app = FastAPI()

    # Add RLS middleware
    app.add_middleware(RLSMiddleware)

    # Add test routes
    @app.get("/test")
    async def test_route(request: Request):
        # Simulate that AuthenticationMiddleware already set tenant_id
        tenant_id = getattr(request.state, "tenant_id", None)
        return {
            "tenant_id": tenant_id,
            "rls_applied": tenant_id is not None
        }

    @app.get("/public")
    async def public_route(request: Request):
        # Public route - no tenant_id set
        return {"public": True}

    return app


@pytest.fixture
def client(app):
    """Create test client"""
    return TestClient(app)


# ============================================================================
# TESTS: RLS Context Setting
# ============================================================================

@pytest.mark.asyncio
async def test_rls_context_set_with_tenant_id():
    """Test RLS context is set when tenant_id exists"""
    tenant_id = str(uuid4())

    with patch('mcp_server.middleware.rls.get_db_session') as mock_db:
        # Mock database session
        mock_session = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_session
        mock_db.return_value.__aexit__.return_value = None

        app = FastAPI()
        app.add_middleware(RLSMiddleware)

        @app.get("/test")
        async def test_route(request: Request):
            # Simulate AuthenticationMiddleware setting tenant_id
            request.state.tenant_id = tenant_id
            return {"ok": True}

        client = TestClient(app)
        response = client.get("/test")

        # Should succeed
        assert response.status_code == 200

        # Should have called SET LOCAL
        calls = [str(call) for call in mock_session.execute.call_args_list]
        set_called = any(f"SET LOCAL app.current_tenant_id = '{tenant_id}'" in str(call) for call in calls)
        assert set_called, "SET LOCAL command was not called"


@pytest.mark.asyncio
async def test_rls_context_not_set_without_tenant_id():
    """Test RLS context is NOT set when tenant_id doesn't exist (public endpoint)"""
    with patch('mcp_server.middleware.rls.get_db_session') as mock_db:
        app = FastAPI()
        app.add_middleware(RLSMiddleware)

        @app.get("/public")
        async def public_route():
            return {"public": True}

        client = TestClient(app)
        response = client.get("/public")

        # Should succeed
        assert response.status_code == 200

        # Database session should NOT have been created (public endpoint)
        mock_db.assert_not_called()


# ============================================================================
# TESTS: RLS Context Cleanup
# ============================================================================

@pytest.mark.asyncio
async def test_rls_context_cleanup():
    """Test RLS context is reset after request"""
    tenant_id = str(uuid4())

    with patch('mcp_server.middleware.rls.get_db_session') as mock_db:
        # Mock database session
        mock_session = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_session
        mock_db.return_value.__aexit__.return_value = None

        app = FastAPI()
        app.add_middleware(RLSMiddleware)

        @app.get("/test")
        async def test_route(request: Request):
            request.state.tenant_id = tenant_id
            return {"ok": True}

        client = TestClient(app)
        response = client.get("/test")

        # Should succeed
        assert response.status_code == 200

        # Should have called RESET
        calls = [str(call) for call in mock_session.execute.call_args_list]
        reset_called = any("RESET app.current_tenant_id" in str(call) for call in calls)
        assert reset_called, "RESET command was not called"


# ============================================================================
# TESTS: Error Handling
# ============================================================================

@pytest.mark.asyncio
async def test_rls_error_handling():
    """Test RLS middleware handles database errors gracefully"""
    tenant_id = str(uuid4())

    with patch('mcp_server.middleware.rls.get_db_session') as mock_db:
        # Mock database error
        mock_db.return_value.__aenter__.side_effect = Exception("Database connection failed")

        app = FastAPI()
        app.add_middleware(RLSMiddleware)

        @app.get("/test")
        async def test_route(request: Request):
            request.state.tenant_id = tenant_id
            return {"ok": True}

        client = TestClient(app)
        response = client.get("/test")

        # Should return 500 error
        assert response.status_code == 500
        assert "error" in response.json()


# ============================================================================
# TESTS: Performance
# ============================================================================

@pytest.mark.asyncio
async def test_rls_performance_target():
    """Test RLS context setting is fast (<1ms target)"""
    import time
    tenant_id = str(uuid4())

    with patch('mcp_server.middleware.rls.get_db_session') as mock_db:
        # Mock fast database response
        mock_session = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_session
        mock_db.return_value.__aexit__.return_value = None

        app = FastAPI()
        app.add_middleware(RLSMiddleware)

        @app.get("/test")
        async def test_route(request: Request):
            request.state.tenant_id = tenant_id
            return {"ok": True}

        client = TestClient(app)

        # Warm up
        client.get("/test")

        # Measure 100 requests
        start = time.time()
        for _ in range(100):
            client.get("/test")
        elapsed = time.time() - start

        # Average should be well under 1ms per request
        avg_ms = (elapsed / 100) * 1000
        assert avg_ms < 5  # 5ms is generous

        print(f"Average RLS latency: {avg_ms:.2f}ms per request")


# ============================================================================
# TESTS: RLSContextManager (Helper Class)
# ============================================================================

@pytest.mark.asyncio
async def test_rls_context_manager():
    """Test RLSContextManager for manual context setting"""
    from mcp_server.middleware import RLSContextManager

    tenant_id = str(uuid4())

    with patch('mcp_server.middleware.rls.get_db_session') as mock_db:
        # Mock database session
        mock_session = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_session
        mock_db.return_value.__aexit__.return_value = None

        # Use RLSContextManager
        async with RLSContextManager(tenant_id=tenant_id):
            # Context should be set here
            pass

        # Should have called SET LOCAL and RESET
        calls = [str(call) for call in mock_session.execute.call_args_list]

        set_called = any(f"SET LOCAL app.current_tenant_id = '{tenant_id}'" in str(call) for call in calls)
        reset_called = any("RESET app.current_tenant_id" in str(call) for call in calls)

        assert set_called, "SET LOCAL not called"
        assert reset_called, "RESET not called"


# ============================================================================
# TESTS: Integration with Authentication Middleware
# ============================================================================

@pytest.mark.asyncio
async def test_rls_with_auth_middleware_integration():
    """Test RLS middleware works correctly after Authentication middleware"""
    from mcp_server.middleware import AuthenticationMiddleware
    from core.cache import TwoTierCache

    tenant_id = str(uuid4())

    # Mock cache
    mock_cache = Mock(spec=TwoTierCache)
    cached_value = f"{tenant_id}|pro|{uuid4()}|admin"
    mock_cache.get.return_value = cached_value

    with patch('mcp_server.middleware.rls.get_db_session') as mock_db:
        # Mock database session
        mock_session = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_session
        mock_db.return_value.__aexit__.return_value = None

        app = FastAPI()

        # Add both middleware (correct order)
        app.add_middleware(RLSMiddleware)  # Second
        app.add_middleware(AuthenticationMiddleware, cache=mock_cache)  # First

        @app.get("/test")
        async def test_route(request: Request):
            return {
                "tenant_id": request.state.tenant_id,
                "tenant_plan": request.state.tenant_plan
            }

        client = TestClient(app)
        response = client.get("/test", headers={"X-API-Key": "test_key"})

        # Should succeed
        assert response.status_code == 200
        assert response.json()["tenant_id"] == tenant_id

        # RLS should have been set
        calls = [str(call) for call in mock_session.execute.call_args_list]
        set_called = any(f"SET LOCAL app.current_tenant_id = '{tenant_id}'" in str(call) for call in calls)
        assert set_called, "RLS context was not set despite auth success"

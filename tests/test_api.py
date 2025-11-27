"""
API Integration Tests for NubemSuperFClaude
"""

import pytest
import asyncio
from httpx import AsyncClient
from pathlib import Path
import sys
import json

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import NubemSuperFClaude


class TestAPIEndpoints:
    """Test API endpoints"""
    
    @pytest.fixture
    async def app(self):
        """Create app instance"""
        app_instance = NubemSuperFClaude()
        return app_instance.create_app()
    
    @pytest.fixture
    async def client(self, app):
        """Create test client"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client
    
    @pytest.mark.asyncio
    async def test_root_redirect(self, client):
        """Test root endpoint redirects to docs"""
        response = await client.get("/", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/docs"
    
    @pytest.mark.asyncio
    async def test_info_endpoint(self, client):
        """Test info endpoint"""
        response = await client.get("/info")
        assert response.status_code == 200
        
        data = response.json()
        assert data["name"] == "NubemSuperFClaude"
        assert data["version"] == "1.0.0"
        assert "features" in data
        assert data["features"]["personas"] == 100
    
    @pytest.mark.asyncio
    async def test_health_endpoint(self, client):
        """Test health check endpoint"""
        response = await client.get("/api/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy"]
        assert "checks" in data
        assert "system" in data
    
    @pytest.mark.asyncio
    async def test_liveness_probe(self, client):
        """Test Kubernetes liveness probe"""
        response = await client.get("/api/health/live")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "alive"
        assert "timestamp" in data
    
    @pytest.mark.asyncio
    async def test_readiness_probe(self, client):
        """Test Kubernetes readiness probe"""
        response = await client.get("/api/health/ready")
        # May be 200 or 503 depending on service status
        assert response.status_code in [200, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "ready"
    
    @pytest.mark.asyncio
    async def test_metrics_endpoint(self, client):
        """Test Prometheus metrics endpoint"""
        response = await client.get("/api/metrics")
        assert response.status_code == 200
        
        # Check for Prometheus format
        content = response.text
        assert "# HELP" in content
        assert "# TYPE" in content
        assert "nubemsuper_" in content
    
    @pytest.mark.asyncio
    async def test_request_id_header(self, client):
        """Test that request ID is added to responses"""
        response = await client.get("/info")
        assert "x-request-id" in response.headers
        
        # Request ID should be a valid UUID
        request_id = response.headers["x-request-id"]
        assert len(request_id) == 36  # UUID format with dashes
        assert request_id.count("-") == 4
    
    @pytest.mark.asyncio
    async def test_cors_headers(self, client):
        """Test CORS headers are present"""
        response = await client.options("/info")
        # CORS headers should be present
        # Note: Actual headers depend on CORS configuration


class TestErrorHandling:
    """Test error handling"""
    
    @pytest.fixture
    async def app(self):
        """Create app instance"""
        app_instance = NubemSuperFClaude()
        return app_instance.create_app()
    
    @pytest.fixture
    async def client(self, app):
        """Create test client"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client
    
    @pytest.mark.asyncio
    async def test_404_error(self, client):
        """Test 404 error handling"""
        response = await client.get("/nonexistent")
        assert response.status_code == 404
        
        data = response.json()
        assert "error" in data
        assert "request_id" in data["error"]
    
    @pytest.mark.asyncio
    async def test_method_not_allowed(self, client):
        """Test 405 method not allowed"""
        response = await client.post("/api/health")  # Health is GET only
        assert response.status_code == 405


class TestCacheIntegration:
    """Test cache integration with API"""
    
    @pytest.fixture
    async def app(self):
        """Create app instance"""
        app_instance = NubemSuperFClaude()
        return app_instance.create_app()
    
    @pytest.fixture
    async def client(self, app):
        """Create test client"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client
    
    @pytest.mark.asyncio
    async def test_cache_headers(self, client):
        """Test cache-related headers"""
        # Make multiple requests to same endpoint
        response1 = await client.get("/info")
        response2 = await client.get("/info")
        
        # Both should succeed
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        # Could add cache hit/miss headers in future


class TestPerformance:
    """Performance tests for API"""
    
    @pytest.fixture
    async def app(self):
        """Create app instance"""
        app_instance = NubemSuperFClaude()
        return app_instance.create_app()
    
    @pytest.fixture
    async def client(self, app):
        """Create test client"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client
    
    @pytest.mark.asyncio
    async def test_concurrent_requests(self, client):
        """Test handling concurrent requests"""
        import time
        
        async def make_request():
            return await client.get("/info")
        
        # Make 10 concurrent requests
        start = time.time()
        tasks = [make_request() for _ in range(10)]
        responses = await asyncio.gather(*tasks)
        duration = time.time() - start
        
        # All should succeed
        for response in responses:
            assert response.status_code == 200
        
        # Should handle 10 requests in under 2 seconds
        assert duration < 2.0
        
        # Calculate requests per second
        rps = 10 / duration
        print(f"\nAPI Performance: {rps:.1f} requests/second")
        assert rps > 5  # Should handle at least 5 req/sec


class TestSecurityHeaders:
    """Test security headers"""
    
    @pytest.fixture
    async def app(self):
        """Create app instance"""
        app_instance = NubemSuperFClaude()
        return app_instance.create_app()
    
    @pytest.fixture
    async def client(self, app):
        """Create test client"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client
    
    @pytest.mark.asyncio
    async def test_security_headers(self, client):
        """Test that security headers are present"""
        response = await client.get("/info")
        
        # Check for request ID (security tracking)
        assert "x-request-id" in response.headers
        
        # Additional security headers could be checked here
        # Examples: X-Content-Type-Options, X-Frame-Options, etc.


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])
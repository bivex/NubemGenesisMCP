"""
Smoke Tests for NubemGenesisMCP Deployment
Tests básicos para verificar que el sistema desplegado está funcionando correctamente
"""
import pytest
import requests
import time

# URL del LoadBalancer desplegado
BASE_URL = "http://34.170.167.74"

class TestDeploymentSmoke:
    """Tests de humo para verificar deployment"""

    def test_health_endpoint_responds(self):
        """Verificar que el endpoint /health responde"""
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        assert response.status_code == 200, f"Health check failed with status {response.status_code}"

    def test_health_endpoint_json_format(self):
        """Verificar que /health devuelve JSON válido"""
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        data = response.json()
        assert "status" in data
        assert "service" in data
        assert "version" in data

    def test_health_status_healthy(self):
        """Verificar que el servicio reporta estado healthy"""
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        data = response.json()
        assert data["status"] == "healthy"

    def test_health_service_name(self):
        """Verificar nombre del servicio"""
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        data = response.json()
        assert "NubemSuperFClaude" in data["service"]

    def test_health_version(self):
        """Verificar versión del servicio"""
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        data = response.json()
        assert data["version"] == "1.2.0-auth"

    def test_health_features_authentication(self):
        """Verificar que autenticación está habilitada"""
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        data = response.json()
        assert "features" in data
        assert data["features"]["authentication"] is True

    def test_personas_endpoint_requires_auth(self):
        """Verificar que /personas requiere autenticación"""
        response = requests.get(f"{BASE_URL}/personas", timeout=10)
        # Debe devolver error de autenticación (no 200)
        assert response.status_code != 200
        data = response.json()
        assert "error" in data or "message" in data

    def test_personas_endpoint_auth_error_message(self):
        """Verificar mensaje de error de autenticación"""
        response = requests.get(f"{BASE_URL}/personas", timeout=10)
        data = response.json()
        assert "authentication" in str(data).lower() or "auth" in str(data).lower()

    def test_mcp_endpoint_requires_auth(self):
        """Verificar que /mcp requiere autenticación"""
        response = requests.post(
            f"{BASE_URL}/mcp",
            json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1},
            timeout=10
        )
        # Debe devolver error de autenticación
        assert response.status_code != 200 or "error" in response.json()

    def test_response_time_acceptable(self):
        """Verificar que el tiempo de respuesta es aceptable (<1s)"""
        start = time.time()
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        duration = time.time() - start
        assert duration < 1.0, f"Response time too slow: {duration}s"
        assert response.status_code == 200

    def test_multiple_requests_stability(self):
        """Verificar estabilidad con múltiples requests"""
        success_count = 0
        for _ in range(10):
            try:
                response = requests.get(f"{BASE_URL}/health", timeout=5)
                if response.status_code == 200:
                    success_count += 1
            except Exception:
                pass
        # Al menos 9 de 10 requests deben tener éxito
        assert success_count >= 9, f"Only {success_count}/10 requests succeeded"

    def test_concurrent_requests(self):
        """Verificar manejo de requests concurrentes"""
        import concurrent.futures

        def make_request():
            try:
                response = requests.get(f"{BASE_URL}/health", timeout=10)
                return response.status_code == 200
            except:
                return False

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request) for _ in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        success_count = sum(results)
        assert success_count >= 4, f"Only {success_count}/5 concurrent requests succeeded"


class TestDeploymentAvailability:
    """Tests de disponibilidad"""

    def test_service_uptime(self):
        """Verificar que el servicio está up"""
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        assert response.status_code == 200

    def test_no_5xx_errors(self):
        """Verificar que no hay errores 5xx"""
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        assert response.status_code < 500

    def test_loadbalancer_accessible(self):
        """Verificar que el LoadBalancer es accesible"""
        try:
            response = requests.get(f"{BASE_URL}/health", timeout=10)
            assert True
        except requests.exceptions.ConnectionError:
            pytest.fail("LoadBalancer is not accessible")


class TestDeploymentSecurity:
    """Tests de seguridad básicos"""

    def test_auth_headers_required_for_protected_endpoints(self):
        """Verificar que endpoints protegidos requieren headers de auth"""
        response = requests.get(f"{BASE_URL}/personas", timeout=10)
        assert response.status_code in [401, 403]  # Unauthorized or Forbidden

    def test_invalid_api_key_rejected(self):
        """Verificar que API keys inválidas son rechazadas"""
        response = requests.get(
            f"{BASE_URL}/personas",
            headers={"X-API-Key": "invalid_key_12345"},
            timeout=10
        )
        assert response.status_code in [401, 403]

    def test_no_sensitive_info_in_errors(self):
        """Verificar que los errores no exponen info sensible"""
        response = requests.get(f"{BASE_URL}/personas", timeout=10)
        data = response.json()
        text = str(data).lower()
        # No debe contener rutas de sistema, passwords, etc
        assert "/app/" not in text
        assert "password" not in text
        assert "secret" not in text


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

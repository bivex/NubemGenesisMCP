#!/usr/bin/env python3
"""
Tests para el cliente OAuth Device Flow

Autor: NubemSystems
Fecha: 2025-10-28
"""

import pytest
import json
import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

# Añadir directorio claude-code-integration al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "claude-code-integration"))

from oauth_device_flow_client import OAuthDeviceFlowClient
from config_manager import ConfigManager


class TestOAuthDeviceFlowClient:
    """Tests para OAuthDeviceFlowClient"""

    @pytest.fixture
    def client(self):
        """Fixture: cliente OAuth"""
        return OAuthDeviceFlowClient(server_endpoint="http://localhost:8000/mcp")

    @pytest.fixture
    def mock_response(self):
        """Fixture: respuesta HTTP mockeada"""
        mock = Mock()
        mock.status_code = 200
        return mock

    def test_initialization(self, client):
        """Test: inicialización del cliente"""
        assert client.server_endpoint == "http://localhost:8000/mcp"
        assert client.timeout == 30
        assert 'Content-Type' in client.session.headers
        assert client.session.headers['Content-Type'] == 'application/json'

    @patch('requests.Session.post')
    def test_request_device_code_success(self, mock_post, client, mock_response):
        """Test: solicitud exitosa de device code"""
        # Configurar respuesta mock
        mock_response.json.return_value = {
            "device_code": "abc123",
            "user_code": "WDJB-MJHT",
            "verification_uri": "https://example.com/device",
            "verification_uri_complete": "https://example.com/device?user_code=WDJB-MJHT",
            "expires_in": 900,
            "interval": 5
        }
        mock_post.return_value = mock_response

        # Ejecutar
        result = client.request_device_code()

        # Verificar
        assert result is not None
        assert result["device_code"] == "abc123"
        assert result["user_code"] == "WDJB-MJHT"
        assert result["expires_in"] == 900
        assert result["interval"] == 5

        # Verificar que se llamó al endpoint correcto
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://localhost:8000/mcp/auth/device/code"
        assert kwargs['json']['client_id'] == "nubemsfc-cli"

    @patch('requests.Session.post')
    def test_request_device_code_rate_limit(self, mock_post, client, mock_response):
        """Test: manejo de rate limit"""
        # Configurar respuesta 429 (rate limit)
        mock_response.status_code = 429
        mock_response.json.return_value = {
            "error": "slow_down",
            "error_description": "Rate limit exceeded"
        }
        mock_post.return_value = mock_response

        # Ejecutar
        result = client.request_device_code()

        # Verificar
        assert result is None

    @patch('requests.Session.post')
    def test_poll_for_token_success(self, mock_post, client, mock_response):
        """Test: polling exitoso (obtiene token)"""
        # Simular respuesta exitosa inmediata
        expires_at = (datetime.utcnow() + timedelta(days=1)).isoformat() + "Z"
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "eyJhbGc...",
            "token_type": "Bearer",
            "expires_at": expires_at,
            "user_email": "test@example.com"
        }
        mock_post.return_value = mock_response

        # Ejecutar (con timeout corto para test)
        result = client.poll_for_token(
            device_code="abc123",
            interval=1,
            expires_in=10
        )

        # Verificar
        assert result is not None
        assert result["access_token"] == "eyJhbGc..."
        assert result["user_email"] == "test@example.com"

    @patch('requests.Session.post')
    @patch('time.sleep')  # Mockear sleep para acelerar test
    def test_poll_for_token_pending_then_success(self, mock_sleep, mock_post, client):
        """Test: polling con authorization_pending luego success"""
        # Simular 2 respuestas pending, luego success
        pending_response = Mock()
        pending_response.status_code = 400
        pending_response.json.return_value = {"error": "authorization_pending"}

        success_response = Mock()
        success_response.status_code = 200
        expires_at = (datetime.utcnow() + timedelta(days=1)).isoformat() + "Z"
        success_response.json.return_value = {
            "access_token": "eyJhbGc...",
            "token_type": "Bearer",
            "expires_at": expires_at,
            "user_email": "test@example.com"
        }

        # Secuencia: pending -> pending -> success
        mock_post.side_effect = [pending_response, pending_response, success_response]

        # Ejecutar
        result = client.poll_for_token(
            device_code="abc123",
            interval=1,
            expires_in=30
        )

        # Verificar
        assert result is not None
        assert result["access_token"] == "eyJhbGc..."
        assert mock_post.call_count == 3
        assert mock_sleep.call_count >= 2

    @patch('requests.Session.post')
    def test_poll_for_token_access_denied(self, mock_post, client, mock_response):
        """Test: polling con acceso denegado"""
        mock_response.status_code = 403
        mock_response.json.return_value = {"error": "access_denied"}
        mock_post.return_value = mock_response

        # Ejecutar
        result = client.poll_for_token(
            device_code="abc123",
            interval=1,
            expires_in=10
        )

        # Verificar
        assert result is None

    @patch('requests.Session.post')
    def test_poll_for_token_expired(self, mock_post, client, mock_response):
        """Test: polling con token expirado"""
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": "expired_token"}
        mock_post.return_value = mock_response

        # Ejecutar
        result = client.poll_for_token(
            device_code="abc123",
            interval=1,
            expires_in=10
        )

        # Verificar
        assert result is None

    def test_save_token(self, client):
        """Test: guardar token en archivo"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"

            # Preparar datos del token
            expires_at = (datetime.utcnow() + timedelta(days=1)).isoformat() + "Z"
            token_data = {
                "access_token": "eyJhbGc...",
                "token_type": "Bearer",
                "expires_at": expires_at,
                "user_email": "test@example.com"
            }

            # Ejecutar
            result = client.save_token(token_data, config_path)

            # Verificar
            assert result is True
            assert config_path.exists()

            # Verificar contenido
            with open(config_path, 'r') as f:
                config = json.load(f)

            assert config["auth"]["token"] == "eyJhbGc..."
            assert config["auth"]["user_email"] == "test@example.com"

            # Verificar permisos (600)
            stat_info = os.stat(config_path)
            permissions = oct(stat_info.st_mode)[-3:]
            assert permissions == "600"

    def test_load_token(self, client):
        """Test: cargar token desde archivo"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"

            # Crear archivo de config
            expires_at = (datetime.utcnow() + timedelta(days=1)).isoformat() + "Z"
            config = {
                "auth": {
                    "method": "oauth",
                    "token": "eyJhbGc...",
                    "token_type": "Bearer",
                    "expires_at": expires_at,
                    "user_email": "test@example.com",
                    "issued_at": datetime.utcnow().isoformat() + "Z"
                }
            }

            with open(config_path, 'w') as f:
                json.dump(config, f)

            # Ejecutar
            result = client.load_token(config_path)

            # Verificar
            assert result is not None
            assert result["token"] == "eyJhbGc..."
            assert result["user_email"] == "test@example.com"

    def test_load_token_not_exists(self, client):
        """Test: cargar token cuando el archivo no existe"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "nonexistent.json"

            # Ejecutar
            result = client.load_token(config_path)

            # Verificar
            assert result is None

    def test_is_token_valid(self, client):
        """Test: verificar validez del token (no expirado)"""
        # Token válido (expira en 1 día)
        expires_at = (datetime.utcnow() + timedelta(days=1)).isoformat() + "Z"
        token_data = {
            "expires_at": expires_at
        }

        result = client.is_token_valid(token_data)
        assert result is True

    def test_is_token_expired(self, client):
        """Test: verificar token expirado"""
        # Token expirado (expiró hace 1 día)
        expires_at = (datetime.utcnow() - timedelta(days=1)).isoformat() + "Z"
        token_data = {
            "expires_at": expires_at
        }

        result = client.is_token_valid(token_data)
        assert result is False

    def test_is_token_expiring_soon(self, client):
        """Test: verificar token próximo a expirar (dentro de margen de 5 min)"""
        # Token expira en 3 minutos (dentro del margen de 5 min)
        expires_at = (datetime.utcnow() + timedelta(minutes=3)).isoformat() + "Z"
        token_data = {
            "expires_at": expires_at
        }

        # Debe retornar False porque está dentro del margen
        result = client.is_token_valid(token_data)
        assert result is False

    def test_get_token_info(self, client):
        """Test: obtener información del token"""
        expires_at = (datetime.utcnow() + timedelta(hours=5, minutes=30)).isoformat() + "Z"
        issued_at = datetime.utcnow().isoformat() + "Z"
        token_data = {
            "method": "oauth",
            "token": "eyJhbGc...",
            "expires_at": expires_at,
            "user_email": "test@example.com",
            "issued_at": issued_at
        }

        result = client.get_token_info(token_data)

        assert result is not None
        assert result["user_email"] == "test@example.com"
        assert result["method"] == "oauth"
        assert result["is_valid"] is True
        assert "5h" in result["time_remaining"]

    def test_revoke_token(self, client):
        """Test: revocar token (eliminar archivo)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"

            # Crear archivo de config
            config = {
                "auth": {
                    "token": "eyJhbGc...",
                }
            }

            with open(config_path, 'w') as f:
                json.dump(config, f)

            assert config_path.exists()

            # Ejecutar
            result = client.revoke_token(config_path)

            # Verificar
            assert result is True
            assert not config_path.exists()


class TestConfigManager:
    """Tests para ConfigManager"""

    @pytest.fixture
    def config_manager(self):
        """Fixture: config manager con directorio temporal"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConfigManager(config_dir=Path(tmpdir))
            yield manager

    def test_initialization(self, config_manager):
        """Test: inicialización del config manager"""
        assert config_manager.config_dir.exists()
        assert config_manager.backup_dir.exists()

    def test_read_default_config(self, config_manager):
        """Test: leer configuración por defecto (archivo no existe)"""
        config = config_manager.read()

        assert config is not None
        assert "auth" in config
        assert "server" in config
        assert config["version"] == "1.0.0"

    def test_write_and_read_config(self, config_manager):
        """Test: escribir y leer configuración"""
        # Preparar config
        config = config_manager._get_default_config()
        config["auth"]["token"] = "test-token"
        config["auth"]["user_email"] = "test@example.com"

        # Escribir
        result = config_manager.write(config)
        assert result is True

        # Leer
        read_config = config_manager.read()
        assert read_config["auth"]["token"] == "test-token"
        assert read_config["auth"]["user_email"] == "test@example.com"

    def test_config_file_permissions(self, config_manager):
        """Test: verificar permisos 600 del archivo de config"""
        config = config_manager._get_default_config()
        config_manager.write(config)

        # Verificar permisos
        stat_info = os.stat(config_manager.config_path)
        permissions = oct(stat_info.st_mode)[-3:]
        assert permissions == "600"

    def test_update_auth(self, config_manager):
        """Test: actualizar solo sección de auth"""
        auth_data = {
            "token": "new-token",
            "user_email": "new@example.com",
            "expires_at": "2025-10-29T00:00:00Z"
        }

        result = config_manager.update_auth(auth_data)
        assert result is True

        # Verificar
        config = config_manager.read()
        assert config["auth"]["token"] == "new-token"
        assert config["auth"]["user_email"] == "new@example.com"

    def test_get_auth(self, config_manager):
        """Test: obtener datos de autenticación"""
        # Sin auth
        auth = config_manager.get_auth()
        assert auth is None

        # Con auth
        config_manager.update_auth({
            "token": "test-token",
            "user_email": "test@example.com"
        })

        auth = config_manager.get_auth()
        assert auth is not None
        assert auth["token"] == "test-token"

    def test_clear_auth(self, config_manager):
        """Test: limpiar autenticación"""
        # Establecer auth
        config_manager.update_auth({
            "token": "test-token",
            "user_email": "test@example.com"
        })

        # Limpiar
        result = config_manager.clear_auth()
        assert result is True

        # Verificar
        auth = config_manager.get_auth()
        assert auth is None

    def test_update_server(self, config_manager):
        """Test: actualizar configuración del servidor"""
        result = config_manager.update_server(
            endpoint="https://example.com/mcp",
            timeout=60
        )
        assert result is True

        # Verificar
        server = config_manager.get_server()
        assert server["endpoint"] == "https://example.com/mcp"
        assert server["timeout"] == 60

    def test_backup_creation(self, config_manager):
        """Test: creación de backups automáticos"""
        # Crear config inicial
        config = config_manager._get_default_config()
        config["auth"]["token"] = "token-1"
        config_manager.write(config, backup=False)

        # Actualizar (debe crear backup)
        config["auth"]["token"] = "token-2"
        config_manager.write(config, backup=True)

        # Verificar que existe backup
        backups = config_manager.list_backups()
        assert len(backups) > 0

    def test_restore_from_backup(self, config_manager):
        """Test: restaurar desde backup"""
        # Crear config original
        config = config_manager._get_default_config()
        config["auth"]["token"] = "original-token"
        config_manager.write(config, backup=False)

        # Actualizar (crear backup)
        config["auth"]["token"] = "updated-token"
        config_manager.write(config, backup=True)

        # Restaurar
        result = config_manager.restore_from_backup()
        assert result is True

        # Verificar que se restauró el original
        restored_config = config_manager.read()
        assert restored_config["auth"]["token"] == "original-token"

    def test_validate_config(self, config_manager):
        """Test: validación de estructura de configuración"""
        # Config válida
        valid_config = config_manager._get_default_config()
        assert config_manager._validate_config(valid_config) is True

        # Config inválida (falta sección auth)
        invalid_config = {"server": {}}
        assert config_manager._validate_config(invalid_config) is False

        # Config inválida (falta endpoint en server)
        invalid_config2 = {
            "auth": {},
            "server": {}
        }
        assert config_manager._validate_config(invalid_config2) is False


class TestIntegration:
    """Tests de integración end-to-end"""

    @patch('requests.Session.post')
    def test_full_login_flow(self, mock_post):
        """Test: flujo completo de login (mock)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"

            # Configurar client
            client = OAuthDeviceFlowClient()

            # Mock request_device_code
            device_response = Mock()
            device_response.status_code = 200
            device_response.json.return_value = {
                "device_code": "abc123",
                "user_code": "WDJB-MJHT",
                "verification_uri": "https://example.com/device",
                "expires_in": 900,
                "interval": 5
            }

            # Mock poll_for_token (éxito inmediato)
            token_response = Mock()
            token_response.status_code = 200
            expires_at = (datetime.utcnow() + timedelta(days=1)).isoformat() + "Z"
            token_response.json.return_value = {
                "access_token": "eyJhbGc...",
                "token_type": "Bearer",
                "expires_at": expires_at,
                "user_email": "test@example.com"
            }

            mock_post.side_effect = [device_response, token_response]

            # 1. Request device code
            device_data = client.request_device_code()
            assert device_data is not None

            # 2. Poll for token
            token_data = client.poll_for_token(
                device_code=device_data["device_code"],
                interval=1,
                expires_in=10
            )
            assert token_data is not None

            # 3. Save token
            result = client.save_token(token_data, config_path)
            assert result is True

            # 4. Verify token is saved
            loaded_token = client.load_token(config_path)
            assert loaded_token is not None
            assert loaded_token["token"] == "eyJhbGc..."

            # 5. Verify token is valid
            assert client.is_token_valid(loaded_token) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

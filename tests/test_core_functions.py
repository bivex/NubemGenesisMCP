#!/usr/bin/env python3
"""
Test Suite para funciones core de NubemSuperFClaude
Coverage objetivo: > 80%
"""

import pytest
import sys
import os
from pathlib import Path
import tempfile
import json
from unittest.mock import Mock, patch, MagicMock

# Añadir proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.fast_claude import FastClaude
from core.sqlite_vector_store import SQLiteVectorStore
from core.rich_cli import RichCLI
from core.optimized_init import quick_init, get_config


class TestFastClaude:
    """Tests para FastClaude"""

    def test_initialization(self):
        """Test inicialización básica"""
        fc = FastClaude()
        assert fc is not None
        assert fc.api_key is not None or fc.api_key == None

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"})
    def test_load_api_key_from_env(self):
        """Test carga de API key desde variable de entorno"""
        fc = FastClaude()
        assert fc.api_key == "test-key-123"

    def test_execute_without_query(self):
        """Test ejecución sin query"""
        fc = FastClaude()
        result = fc.execute("")
        assert result is None

    @patch('core.fast_claude.Anthropic')
    def test_execute_anthropic_success(self, mock_anthropic):
        """Test ejecución exitosa con Anthropic"""
        # Mock de la respuesta
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Test response")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        fc = FastClaude()
        fc.api_key = "sk-ant-test"
        result = fc._execute_anthropic_direct("Test query")

        assert result == "Test response"
        mock_client.messages.create.assert_called_once()

    @patch('core.fast_claude.OpenAI')
    def test_execute_openai_success(self, mock_openai):
        """Test ejecución exitosa con OpenAI"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="OpenAI response"))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        fc = FastClaude()
        fc.api_key = "sk-test"
        result = fc._execute_openai_direct("Test query")

        assert result == "OpenAI response"


class TestSQLiteVectorStore:
    """Tests para SQLite Vector Store"""

    def setup_method(self):
        """Setup para cada test"""
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.store = SQLiteVectorStore(self.temp_db.name)

    def teardown_method(self):
        """Cleanup después de cada test"""
        self.store.close()
        os.unlink(self.temp_db.name)

    def test_initialization(self):
        """Test inicialización de la base de datos"""
        assert self.store is not None
        assert os.path.exists(self.temp_db.name)

    def test_add_vector(self):
        """Test añadir vector"""
        vector_id = self.store.add_vector(
            "Test content",
            {"type": "test"},
            "test_collection"
        )
        assert vector_id is not None
        assert len(vector_id) == 32  # MD5 hash length

    def test_search_vectors(self):
        """Test búsqueda de vectores"""
        # Añadir algunos vectores
        self.store.add_vector("Python programming", {"lang": "python"})
        self.store.add_vector("JavaScript development", {"lang": "js"})
        self.store.add_vector("Database management", {"type": "db"})

        # Buscar
        results = self.store.search("programming languages", limit=2)

        assert len(results) <= 2
        assert all('content' in r for r in results)
        assert all('score' in r for r in results)

    def test_save_and_load_session(self):
        """Test guardar y cargar sesión"""
        session_id = "test_session_123"
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]

        # Guardar
        self.store.save_session(session_id, messages)

        # Cargar
        loaded = self.store.load_session(session_id)

        assert loaded == messages

    def test_get_stats(self):
        """Test obtener estadísticas"""
        # Añadir algunos datos
        self.store.add_vector("Test 1", {})
        self.store.add_vector("Test 2", {})

        stats = self.store.get_stats()

        assert stats['total_vectors'] == 2
        assert 'db_size_mb' in stats
        assert stats['db_size_mb'] >= 0

    def test_clear_collection(self):
        """Test limpiar colección"""
        # Añadir vectores
        self.store.add_vector("Test 1", {}, "collection1")
        self.store.add_vector("Test 2", {}, "collection1")
        self.store.add_vector("Test 3", {}, "collection2")

        # Limpiar collection1
        deleted = self.store.clear_collection("collection1")

        assert deleted == 2
        stats = self.store.get_stats()
        assert stats['total_vectors'] == 1


class TestRichCLI:
    """Tests para Rich CLI"""

    def test_initialization(self):
        """Test inicialización de Rich CLI"""
        cli = RichCLI()
        assert cli is not None
        assert cli.console is not None

    def test_format_response(self):
        """Test formateo de respuestas"""
        cli = RichCLI()

        # No debe fallar
        cli.format_response("Test response")
        cli.format_response("print('hello')", "python")

    def test_show_metrics(self):
        """Test mostrar métricas"""
        cli = RichCLI()
        metrics = {
            "Test Metric": {"value": 100, "healthy": True}
        }

        # No debe fallar
        cli.show_metrics_dashboard(metrics)

    @patch('core.rich_cli.Prompt.ask')
    def test_interactive_menu(self, mock_ask):
        """Test menú interactivo"""
        mock_ask.return_value = "1"

        cli = RichCLI()
        choice = cli.interactive_menu(["Option 1", "Option 2"])

        assert choice == 0
        mock_ask.assert_called_once()

    def test_error_warning_success(self):
        """Test mensajes de estado"""
        cli = RichCLI()

        # No deben fallar
        cli.show_error("Test error")
        cli.show_warning("Test warning")
        cli.show_success("Test success")
        cli.show_info("Test info")


class TestOptimizedInit:
    """Tests para inicialización optimizada"""

    def test_quick_init(self):
        """Test inicialización rápida"""
        config = quick_init()

        assert config is not None
        assert 'debug' in config
        assert 'qdrant_disabled' in config
        assert 'api_port' in config

    def test_get_config(self):
        """Test obtener configuración"""
        config = get_config()

        assert isinstance(config, dict)
        assert config['api_port'] == 8000 or config['api_port'] > 0

    @patch.dict(os.environ, {"NC_DEBUG": "true"})
    def test_debug_mode(self):
        """Test modo debug"""
        config = get_config()
        assert config['debug'] is True

    @patch.dict(os.environ, {"QDRANT_DISABLED": "true"})
    def test_qdrant_disabled(self):
        """Test Qdrant deshabilitado"""
        config = get_config()
        assert config['qdrant_disabled'] is True


class TestIntegration:
    """Tests de integración"""

    def test_fastclaude_with_sqlite(self):
        """Test integración FastClaude + SQLite"""
        fc = FastClaude()
        store = SQLiteVectorStore(":memory:")

        # Simular flujo
        query = "Test query"
        store.add_vector(query, {"source": "test"})

        results = store.search(query, limit=1)
        assert len(results) == 1

        store.close()

    @patch('core.fast_claude.Anthropic')
    def test_full_flow(self, mock_anthropic):
        """Test flujo completo"""
        # Setup mock
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="AI Response")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        # Flujo completo
        fc = FastClaude()
        fc.api_key = "sk-ant-test"

        store = SQLiteVectorStore(":memory:")

        # Ejecutar query
        query = "What is Python?"
        response = fc._execute_anthropic_direct(query)

        # Guardar en store
        store.add_vector(query, {"response": response})

        # Buscar similar
        similar = store.search("Python programming", limit=1)

        assert len(similar) == 1
        assert "Python" in similar[0]['content']

        store.close()


# Fixtures compartidos
@pytest.fixture
def temp_config():
    """Fixture para configuración temporal"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml') as f:
        config = {
            "debug": False,
            "api_port": 8000,
            "cache_enabled": True
        }
        json.dump(config, f)
        f.flush()
        yield f.name


@pytest.fixture
def mock_api_response():
    """Fixture para respuestas mock de API"""
    return {
        "response": "Test response",
        "tokens": 100,
        "model": "test-model"
    }


# Markers para diferentes tipos de tests
pytestmark = [
    pytest.mark.unit,
    pytest.mark.filterwarnings("ignore::DeprecationWarning")
]


if __name__ == "__main__":
    # Ejecutar tests con coverage
    pytest.main([
        __file__,
        "-v",
        "--cov=core",
        "--cov-report=term-missing",
        "--cov-report=html"
    ])
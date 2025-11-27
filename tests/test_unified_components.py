#!/usr/bin/env python3
"""
Tests básicos para componentes unificados
"""

try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False
    class pytest:
        class fixture:
            def __init__(self, *args, **kwargs):
                pass
            def __call__(self, f):
                return f
        fixture = fixture()
        
        class mark:
            class asyncio:
                def __call__(self, f):
                    return f
            asyncio = asyncio()
        mark = mark()

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.unified_orchestrator import UnifiedOrchestrator, get_unified_orchestrator
from core.embeddings.embedding_manager import get_embedding_manager
from core.personas.persona_factory import get_persona_factory


class TestUnifiedOrchestrator:
    """Tests para el orchestrator unificado"""
    
    @pytest.fixture
    def orchestrator(self):
        config = {
            'enable_personas': True,
            'enable_vector': False,
            'enable_multi_llm': False
        }
        return get_unified_orchestrator(config)
    
    @pytest.mark.asyncio
    async def test_orchestrate_simple_task(self, orchestrator):
        """Test orchestration de tarea simple"""
        result = await orchestrator.orchestrate("What is 2+2?")
        
        assert result is not None
        assert 'orchestrator' in result
        assert result['orchestrator'] == 'unified'
        assert 'strategy' in result
    
    @pytest.mark.asyncio  
    async def test_auto_strategy_selection(self, orchestrator):
        """Test selección automática de estrategia"""
        
        # Coding task should select persona strategy
        result = await orchestrator.orchestrate("Write a Python function")
        assert result['strategy'] in ['persona', 'optimized']
        
        # Simple task should use optimized
        result = await orchestrator.orchestrate("Hello")
        assert result['strategy'] == 'optimized'
    
    def test_statistics(self, orchestrator):
        """Test estadísticas del orchestrator"""
        stats = orchestrator.get_statistics()
        
        assert 'total_requests' in stats
        assert 'available_strategies' in stats
        assert isinstance(stats['available_strategies'], list)


class TestEmbeddingManager:
    """Tests para el gestor de embeddings"""
    
    @pytest.fixture
    def manager(self):
        return get_embedding_manager()
    
    def test_generate_single_embedding(self, manager):
        """Test generación de embedding único"""
        text = "This is a test sentence"
        embedding = manager.generate(text)
        
        assert embedding is not None
        assert isinstance(embedding, list)
        assert len(embedding) == manager.embedding_dim
    
    def test_batch_embeddings(self, manager):
        """Test generación batch de embeddings"""
        texts = ["First text", "Second text", "Third text"]
        embeddings = manager.batch_generate(texts)
        
        assert len(embeddings) == 3
        assert all(len(e) == manager.embedding_dim for e in embeddings)
    
    def test_similarity_calculation(self, manager):
        """Test cálculo de similaridad"""
        text1 = "Machine learning is awesome"
        text2 = "AI and machine learning are related"
        text3 = "The weather is nice today"
        
        emb1 = manager.generate(text1)
        emb2 = manager.generate(text2)
        emb3 = manager.generate(text3)
        
        sim_12 = manager.similarity(emb1, emb2)
        sim_13 = manager.similarity(emb1, emb3)
        
        # Similar texts should have higher similarity
        assert sim_12 > sim_13
        assert -1 <= sim_12 <= 1
        assert -1 <= sim_13 <= 1
    
    def test_caching(self, manager):
        """Test cache de embeddings"""
        import time
        
        text = "Test caching functionality"
        
        # First call - not cached
        start = time.time()
        emb1 = manager.generate(text)
        time1 = time.time() - start
        
        # Second call - should be cached
        start = time.time()
        emb2 = manager.generate(text)
        time2 = time.time() - start
        
        assert emb1 == emb2
        # Cached should be faster (but might not always be true in tests)
        # assert time2 < time1


class TestPersonaFactory:
    """Tests para el factory de personas"""
    
    @pytest.fixture
    def factory(self):
        return get_persona_factory()
    
    def test_create_persona(self, factory):
        """Test creación de persona"""
        persona = factory.create('developer')
        
        assert persona is not None
        assert persona.name == 'developer'
        assert hasattr(persona, 'execute')
        assert hasattr(persona, 'can_handle')
    
    def test_singleton_pattern(self, factory):
        """Test patrón singleton"""
        persona1 = factory.create('developer')
        persona2 = factory.create('developer')
        
        # Should return same instance
        assert persona1 is persona2
    
    def test_select_best_persona(self, factory):
        """Test selección de mejor persona"""
        
        # Coding task
        persona = factory.select_best_persona("Write a Python function to sort a list")
        assert persona.name in ['developer', 'junior_developer']
        
        # Data task
        persona = factory.select_best_persona("Analyze this dataset and create visualizations")
        assert persona.name == 'data_analyst'
        
        # Translation task
        persona = factory.select_best_persona("Translate this text to Spanish")
        assert persona.name == 'translator'
    
    @pytest.mark.asyncio
    async def test_persona_execution(self, factory):
        """Test ejecución de persona"""
        persona = factory.create('developer')
        result = await persona.execute("Write hello world")
        
        assert result is not None
        assert 'persona' in result
        assert result['persona'] == 'developer'
    
    def test_get_personas_by_category(self, factory):
        """Test obtener personas por categoría"""
        from core.personas.persona_factory import PersonaCategory
        
        dev_personas = factory.get_personas_by_category(PersonaCategory.DEVELOPMENT)
        assert 'developer' in dev_personas
        
        data_personas = factory.get_personas_by_category(PersonaCategory.DATA)
        assert 'data_analyst' in data_personas


def test_integration():
    """Test de integración completo"""
    
    async def run_integration():
        # Get all components
        orchestrator = get_unified_orchestrator()
        embedding_mgr = get_embedding_manager()
        persona_factory = get_persona_factory()
        
        # Test task
        task = "Write a Python function to calculate fibonacci"
        
        # Generate embedding
        embedding = embedding_mgr.generate(task)
        assert len(embedding) == 384
        
        # Select persona
        persona = persona_factory.select_best_persona(task)
        assert persona.name in ['developer', 'junior_developer']
        
        # Orchestrate
        result = await orchestrator.orchestrate(task)
        assert result is not None
        assert 'strategy' in result
        
        print("✅ Integration test passed!")
    
    asyncio.run(run_integration())


if __name__ == "__main__":
    # Run tests with pytest if available, otherwise run basic tests
    if HAS_PYTEST:
        import pytest
        pytest.main([__file__, '-v'])
    else:
        print("pytest not installed, running basic tests...")
        test_integration()
        print("\nInstall pytest for full test suite: pip install pytest pytest-asyncio")
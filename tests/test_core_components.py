#!/usr/bin/env python3
"""
Comprehensive tests for core components
Target: 80% code coverage
"""

import pytest
import asyncio
import json
import tempfile
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.unified_orchestrator import (
    UnifiedOrchestrator,
    PersonaStrategy,
    VectorStrategy,
    MultiLLMStrategy,
    OptimizedStrategy,
    TaskAnalyzer
)
from core.embeddings.embedding_manager import EmbeddingManager, get_embedding_manager
from core.personas.persona_factory import (
    PersonaFactory,
    BasePersona,
    PersonaLevel,
    PersonaCategory,
    get_persona_factory
)


class TestUnifiedOrchestrator:
    """Test suite for UnifiedOrchestrator"""
    
    @pytest.fixture
    def orchestrator(self):
        config = {
            'enable_personas': True,
            'enable_vector': False,
            'enable_multi_llm': False,
            'enable_optimized': True
        }
        return UnifiedOrchestrator(config)
    
    @pytest.mark.asyncio
    async def test_orchestrate_with_persona_strategy(self, orchestrator):
        """Test orchestration with persona strategy"""
        result = await orchestrator.orchestrate(
            task="Write a Python function",
            strategy="persona"
        )
        
        assert result is not None
        assert 'strategy' in result
        assert result['strategy'] == 'persona'
        assert 'orchestrator' in result
        assert result['orchestrator'] == 'unified'
    
    @pytest.mark.asyncio
    async def test_auto_strategy_selection(self, orchestrator):
        """Test automatic strategy selection based on task"""
        # Coding task should select persona
        result = await orchestrator.orchestrate("Write code for sorting")
        assert result['strategy'] in ['persona', 'optimized']
        
        # Simple task should use optimized
        result = await orchestrator.orchestrate("What is 2+2?")
        assert result['strategy'] == 'optimized'
    
    @pytest.mark.asyncio
    async def test_fallback_on_error(self, orchestrator):
        """Test fallback to default strategy on error"""
        with patch.object(PersonaStrategy, 'orchestrate', side_effect=Exception("Test error")):
            result = await orchestrator.orchestrate(
                task="Test task",
                strategy="persona"
            )
            # Should fallback to optimized
            assert result['strategy'] == 'optimized'
    
    def test_add_remove_strategy(self, orchestrator):
        """Test adding and removing strategies"""
        # Add custom strategy
        mock_strategy = Mock()
        mock_strategy.get_name.return_value = "custom"
        
        orchestrator.add_strategy("custom", mock_strategy)
        assert "custom" in orchestrator.strategies
        
        # Remove strategy
        orchestrator.remove_strategy("custom")
        assert "custom" not in orchestrator.strategies
    
    def test_statistics_tracking(self, orchestrator):
        """Test statistics tracking"""
        stats = orchestrator.get_statistics()
        
        assert 'total_requests' in stats
        assert 'strategy_usage' in stats
        assert 'available_strategies' in stats
        assert isinstance(stats['available_strategies'], list)


class TestEmbeddingManager:
    """Test suite for EmbeddingManager"""
    
    @pytest.fixture
    def manager(self):
        return get_embedding_manager()
    
    def test_singleton_pattern(self):
        """Test that EmbeddingManager is a singleton"""
        manager1 = get_embedding_manager()
        manager2 = get_embedding_manager()
        assert manager1 is manager2
    
    def test_generate_single_embedding(self, manager):
        """Test generating a single embedding"""
        text = "Test embedding generation"
        embedding = manager.generate(text)
        
        assert embedding is not None
        assert isinstance(embedding, list)
        assert len(embedding) == manager.embedding_dim
        assert all(isinstance(x, float) for x in embedding)
    
    def test_batch_generate(self, manager):
        """Test batch embedding generation"""
        texts = ["First text", "Second text", "Third text"]
        embeddings = manager.batch_generate(texts)
        
        assert len(embeddings) == 3
        assert all(len(e) == manager.embedding_dim for e in embeddings)
    
    def test_embedding_cache(self, manager):
        """Test embedding cache functionality"""
        text = "Cached embedding test"
        
        # First call - not cached
        embedding1 = manager.generate(text)
        
        # Second call - should be cached
        embedding2 = manager.generate(text)
        
        assert embedding1 == embedding2
    
    def test_similarity_calculation(self, manager):
        """Test similarity calculation between embeddings"""
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
    
    def test_find_similar(self, manager):
        """Test finding similar embeddings"""
        query = manager.generate("Python programming")
        candidates = [
            manager.generate("Python coding tutorial"),
            manager.generate("JavaScript development"),
            manager.generate("Coffee brewing guide")
        ]
        
        similar = manager.find_similar(query, candidates, top_k=2)
        
        assert len(similar) == 2
        assert similar[0][1] > similar[1][1]  # First should be most similar
    
    def test_backend_switching(self, manager):
        """Test switching between backends"""
        original_backend = manager._backend
        
        # Switch to hash backend
        manager.set_backend('hash')
        assert manager._backend == 'hash'
        
        # Generate embedding with hash backend
        embedding = manager.generate("Test with hash backend")
        assert len(embedding) == manager.embedding_dim
        
        # Restore original backend
        manager.set_backend(original_backend)


class TestPersonaFactory:
    """Test suite for PersonaFactory"""
    
    @pytest.fixture
    def factory(self):
        return get_persona_factory()
    
    def test_singleton_pattern(self):
        """Test that PersonaFactory is a singleton"""
        factory1 = get_persona_factory()
        factory2 = get_persona_factory()
        assert factory1 is factory2
    
    def test_create_persona(self, factory):
        """Test creating different personas"""
        developer = factory.create('developer')
        assert developer is not None
        assert developer.name == 'developer'
        assert developer.level == PersonaLevel.L4_LEAD
        assert developer.category == PersonaCategory.DEVELOPMENT
    
    def test_persona_reuse(self, factory):
        """Test that personas are reused (singleton per type)"""
        dev1 = factory.create('developer')
        dev2 = factory.create('developer')
        assert dev1 is dev2
    
    @pytest.mark.asyncio
    async def test_persona_execution(self, factory):
        """Test persona task execution"""
        developer = factory.create('developer')
        result = await developer.execute(
            "Write a function to calculate factorial",
            {'language': 'python'}
        )
        
        assert result is not None
        assert 'persona' in result
        assert result['persona'] == 'developer'
        assert 'task_type' in result
    
    def test_persona_can_handle(self, factory):
        """Test persona task matching"""
        developer = factory.create('developer')
        
        # Should handle coding tasks well
        coding_score = developer.can_handle("Write Python code for sorting")
        assert coding_score > 0.5
        
        # Should handle non-coding tasks poorly
        cooking_score = developer.can_handle("Recipe for chocolate cake")
        assert cooking_score < 0.5
    
    def test_select_best_persona(self, factory):
        """Test automatic persona selection"""
        # Coding task
        persona = factory.select_best_persona("Write a Python function")
        assert persona.name in ['developer', 'junior_developer']
        
        # Data task
        persona = factory.select_best_persona("Analyze this dataset")
        assert persona.name == 'data_analyst'
        
        # Translation task
        persona = factory.select_best_persona("Translate to Spanish")
        assert persona.name == 'translator'
    
    def test_get_personas_by_category(self, factory):
        """Test filtering personas by category"""
        dev_personas = factory.get_personas_by_category(PersonaCategory.DEVELOPMENT)
        assert 'developer' in dev_personas
        assert 'junior_developer' in dev_personas
        
        data_personas = factory.get_personas_by_category(PersonaCategory.DATA)
        assert 'data_analyst' in data_personas
    
    def test_get_personas_by_level(self, factory):
        """Test filtering personas by level"""
        senior_personas = factory.get_personas_by_level(PersonaLevel.L3_SENIOR)
        assert len(senior_personas) > 0
        
        lead_personas = factory.get_personas_by_level(PersonaLevel.L4_LEAD)
        assert 'developer' in lead_personas
    
    def test_persona_statistics(self, factory):
        """Test persona usage statistics"""
        # Create and use some personas
        dev = factory.create('developer')
        dev.usage_count = 5
        dev.success_rate = 0.8
        
        stats = factory.get_statistics()
        
        assert 'total_personas' in stats
        assert 'total_usage' in stats
        assert 'personas' in stats
        
        if 'developer' in stats['personas']:
            assert stats['personas']['developer']['usage_count'] == 5


class TestTaskAnalyzer:
    """Test suite for TaskAnalyzer"""
    
    @pytest.fixture
    def analyzer(self):
        return TaskAnalyzer()
    
    def test_analyze_coding_task(self, analyzer):
        """Test analyzing coding tasks"""
        result = analyzer.analyze("Write a Python function for sorting", {})
        
        assert result['task_type'] == 'coding'
        assert result['complexity'] > 3
        assert 'keywords' in result
    
    def test_analyze_data_task(self, analyzer):
        """Test analyzing data tasks"""
        result = analyzer.analyze("Analyze sales data and create charts", {})
        
        assert result['task_type'] == 'data'
    
    def test_analyze_translation_task(self, analyzer):
        """Test analyzing translation tasks"""
        result = analyzer.analyze("Translate this text to French", {})
        
        assert result['task_type'] == 'translation'
    
    def test_complexity_estimation(self, analyzer):
        """Test task complexity estimation"""
        simple = analyzer.analyze("What is 2+2?", {})
        complex = analyzer.analyze("X" * 500, {})  # Long task
        
        assert simple['complexity'] < complex['complexity']
        assert 1 <= simple['complexity'] <= 10
        assert 1 <= complex['complexity'] <= 10


class TestIntegration:
    """Integration tests for the full system"""
    
    @pytest.mark.asyncio
    async def test_full_orchestration_flow(self):
        """Test complete orchestration flow"""
        orchestrator = UnifiedOrchestrator({
            'enable_personas': True,
            'enable_optimized': True
        })
        
        # Test a coding task
        result = await orchestrator.orchestrate(
            task="Write a Python function to reverse a string",
            context={'priority': 'quality'}
        )
        
        assert result['orchestrator'] == 'unified'
        assert 'strategy' in result
        assert 'execution_time' in result
        assert 'timestamp' in result
    
    @pytest.mark.asyncio
    async def test_caching_integration(self):
        """Test caching across components"""
        orchestrator = UnifiedOrchestrator()
        
        # First call
        result1 = await orchestrator.orchestrate("Test caching")
        
        # Second call - might use cache
        result2 = await orchestrator.orchestrate("Test caching")
        
        # Results should be consistent
        assert result1['strategy'] == result2['strategy']
    
    def test_embedding_persona_integration(self):
        """Test integration between embedding manager and persona factory"""
        manager = get_embedding_manager()
        factory = get_persona_factory()
        
        # Generate embeddings for persona descriptions
        personas = factory.get_all_personas()
        embeddings = {}
        
        for name in personas[:3]:  # Test first 3
            persona = factory.create(name)
            embedding = manager.generate(persona.metadata.description)
            embeddings[name] = embedding
        
        # All embeddings should be valid
        assert all(len(e) == manager.embedding_dim for e in embeddings.values())


# Performance tests
class TestPerformance:
    """Performance and load tests"""
    
    @pytest.mark.slow
    def test_embedding_generation_speed(self):
        """Test embedding generation performance"""
        import time
        manager = get_embedding_manager()
        
        texts = ["Test text " + str(i) for i in range(100)]
        
        start = time.time()
        embeddings = manager.batch_generate(texts)
        duration = time.time() - start
        
        assert len(embeddings) == 100
        assert duration < 10  # Should complete in under 10 seconds
    
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_concurrent_orchestration(self):
        """Test concurrent orchestration requests"""
        orchestrator = UnifiedOrchestrator()
        
        tasks = [
            orchestrator.orchestrate(f"Task {i}")
            for i in range(10)
        ]
        
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 10
        assert all('strategy' in r for r in results)


if __name__ == "__main__":
    pytest.main([__file__, '-v', '--cov=core', '--cov-report=term-missing'])
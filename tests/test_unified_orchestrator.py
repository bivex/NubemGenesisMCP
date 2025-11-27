#!/usr/bin/env python3
"""
Tests completos para UnifiedOrchestrator
Objetivo: 80%+ cobertura
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.unified_orchestrator import (
    UnifiedOrchestrator,
    PersonaStrategy,
    VectorStrategy,
    MultiLLMStrategy,
    OptimizedStrategy,
    TaskAnalyzer,
    OrchestrationStrategy
)


class TestBaseStrategy:
    """Tests para BaseStrategy"""
    
    @pytest.mark.asyncio
    async def test_base_strategy_interface(self):
        """Test that BaseStrategy defines the interface"""
        strategy = BaseStrategy()
        
        with pytest.raises(NotImplementedError):
            await strategy.orchestrate("test", {})
        
        assert strategy.get_name() == "base"


class TestPersonaStrategy:
    """Tests para PersonaStrategy"""
    
    @pytest.fixture
    def strategy(self):
        return PersonaStrategy()
    
    @pytest.mark.asyncio
    async def test_orchestrate_with_developer_task(self, strategy):
        """Test orchestration with developer persona"""
        result = await strategy.orchestrate(
            "Write a Python function to sort a list",
            {"priority": "quality"}
        )
        
        assert result is not None
        assert "persona" in result
        assert result["persona"] in ["developer", "junior_developer"]
        assert "strategy" in result
        assert result["strategy"] == "persona"
    
    @pytest.mark.asyncio
    async def test_orchestrate_with_data_task(self, strategy):
        """Test orchestration with data analyst persona"""
        result = await strategy.orchestrate(
            "Analyze this dataset and create visualizations",
            {}
        )
        
        assert result["persona"] == "data_analyst"
    
    @pytest.mark.asyncio
    async def test_orchestrate_with_translation_task(self, strategy):
        """Test orchestration with translator persona"""
        result = await strategy.orchestrate(
            "Translate this text to Spanish",
            {"target_language": "es"}
        )
        
        assert result["persona"] == "translator"
    
    @pytest.mark.asyncio
    async def test_error_handling(self, strategy):
        """Test error handling in PersonaStrategy"""
        with patch('core.personas.persona_factory.get_persona_factory') as mock_factory:
            mock_factory.side_effect = Exception("Factory error")
            
            result = await strategy.orchestrate("test task", {})
            
            assert "error" in result
            assert "Factory error" in result["error"]


class TestVectorStrategy:
    """Tests para VectorStrategy"""
    
    @pytest.fixture
    def strategy(self):
        return VectorStrategy()
    
    @pytest.mark.asyncio
    async def test_orchestrate_basic(self, strategy):
        """Test basic vector orchestration"""
        result = await strategy.orchestrate(
            "Find similar documents about machine learning",
            {}
        )
        
        assert result is not None
        assert result["strategy"] == "vector"
        assert "embeddings" in result
    
    @pytest.mark.asyncio
    async def test_orchestrate_with_similarity_search(self, strategy):
        """Test vector orchestration with similarity search"""
        context = {
            "documents": ["doc1", "doc2", "doc3"],
            "threshold": 0.8
        }
        
        result = await strategy.orchestrate(
            "Find similar content",
            context
        )
        
        assert "similarity_search" in result
        assert result["similarity_search"] is True
    
    @pytest.mark.asyncio
    async def test_error_recovery(self, strategy):
        """Test error recovery in VectorStrategy"""
        with patch('core.embeddings.embedding_manager.get_embedding_manager') as mock_manager:
            mock_manager.side_effect = Exception("Embedding error")
            
            result = await strategy.orchestrate("test", {})
            
            # Should fallback gracefully
            assert result is not None
            assert result["strategy"] == "vector"


class TestMultiLLMStrategy:
    """Tests para MultiLLMStrategy"""
    
    @pytest.fixture
    def strategy(self):
        return MultiLLMStrategy()
    
    @pytest.mark.asyncio
    async def test_orchestrate_with_multiple_providers(self, strategy):
        """Test orchestration with multiple LLM providers"""
        with patch.object(strategy, '_query_providers', new_callable=AsyncMock) as mock_query:
            mock_query.return_value = [
                {"provider": "anthropic", "response": "Response 1"},
                {"provider": "openai", "response": "Response 2"}
            ]
            
            result = await strategy.orchestrate(
                "Complex question requiring consensus",
                {}
            )
            
            assert result["strategy"] == "multi_llm"
            assert "consensus" in result
            assert len(result["responses"]) == 2
    
    @pytest.mark.asyncio
    async def test_consensus_building(self, strategy):
        """Test consensus building from multiple responses"""
        responses = [
            {"provider": "provider1", "response": "Answer A", "confidence": 0.9},
            {"provider": "provider2", "response": "Answer A", "confidence": 0.8},
            {"provider": "provider3", "response": "Answer B", "confidence": 0.7}
        ]
        
        consensus = strategy._build_consensus(responses)
        
        assert consensus is not None
        assert "Answer A" in consensus  # Most common answer
    
    @pytest.mark.asyncio
    async def test_fallback_on_no_providers(self, strategy):
        """Test fallback when no providers available"""
        with patch.object(strategy, '_query_providers', new_callable=AsyncMock) as mock_query:
            mock_query.return_value = []
            
            result = await strategy.orchestrate("test", {})
            
            assert result["strategy"] == "multi_llm"
            assert "fallback" in result or "error" in result


class TestOptimizedStrategy:
    """Tests para OptimizedStrategy"""
    
    @pytest.fixture
    def strategy(self):
        return OptimizedStrategy()
    
    @pytest.mark.asyncio
    async def test_simple_task_optimization(self, strategy):
        """Test optimization for simple tasks"""
        result = await strategy.orchestrate(
            "What is 2+2?",
            {}
        )
        
        assert result["strategy"] == "optimized"
        assert "optimization" in result
        assert result["optimization"] == "simple_task"
    
    @pytest.mark.asyncio
    async def test_complex_task_delegation(self, strategy):
        """Test delegation of complex tasks"""
        result = await strategy.orchestrate(
            "X" * 1000,  # Long complex task
            {"priority": "quality"}
        )
        
        assert result["optimization"] in ["complex_task", "delegated"]
    
    @pytest.mark.asyncio
    async def test_caching_mechanism(self, strategy):
        """Test caching in optimized strategy"""
        task = "Cached task"
        
        # First call
        result1 = await strategy.orchestrate(task, {})
        
        # Second call should use cache
        with patch.object(strategy, '_check_cache', return_value=result1):
            result2 = await strategy.orchestrate(task, {})
        
        assert result1 == result2


class TestTaskAnalyzer:
    """Tests para TaskAnalyzer"""
    
    @pytest.fixture
    def analyzer(self):
        return TaskAnalyzer()
    
    def test_analyze_coding_task(self, analyzer):
        """Test analysis of coding tasks"""
        result = analyzer.analyze(
            "Write a Python function to implement quicksort",
            {}
        )
        
        assert result["task_type"] == "coding"
        assert result["complexity"] > 5
        assert "python" in [k.lower() for k in result["keywords"]]
    
    def test_analyze_data_task(self, analyzer):
        """Test analysis of data tasks"""
        result = analyzer.analyze(
            "Analyze sales data and create charts with trends",
            {}
        )
        
        assert result["task_type"] == "data"
        assert "analyze" in [k.lower() for k in result["keywords"]]
    
    def test_analyze_translation_task(self, analyzer):
        """Test analysis of translation tasks"""
        result = analyzer.analyze(
            "Translate this document from English to French",
            {"source_language": "en", "target_language": "fr"}
        )
        
        assert result["task_type"] == "translation"
        assert result["languages"] == ["en", "fr"]
    
    def test_analyze_creative_task(self, analyzer):
        """Test analysis of creative tasks"""
        result = analyzer.analyze(
            "Write a creative story about space exploration",
            {}
        )
        
        assert result["task_type"] == "creative"
    
    def test_complexity_calculation(self, analyzer):
        """Test complexity calculation"""
        simple = analyzer.analyze("What is 2+2?", {})
        medium = analyzer.analyze("Explain quantum mechanics", {})
        complex = analyzer.analyze("X" * 1000 + " with multiple requirements", {})
        
        assert simple["complexity"] < medium["complexity"]
        assert medium["complexity"] < complex["complexity"]
        assert 1 <= simple["complexity"] <= 10
        assert 1 <= complex["complexity"] <= 10
    
    def test_keyword_extraction(self, analyzer):
        """Test keyword extraction"""
        result = analyzer.analyze(
            "Python machine learning tensorflow keras",
            {}
        )
        
        keywords_lower = [k.lower() for k in result["keywords"]]
        assert "python" in keywords_lower
        assert "machine" in keywords_lower or "learning" in keywords_lower


class TestUnifiedOrchestratorIntegration:
    """Integration tests for UnifiedOrchestrator"""
    
    @pytest.fixture
    def orchestrator(self):
        config = {
            'enable_personas': True,
            'enable_vector': True,
            'enable_multi_llm': True,
            'enable_optimized': True
        }
        return UnifiedOrchestrator(config)
    
    @pytest.mark.asyncio
    async def test_auto_strategy_selection(self, orchestrator):
        """Test automatic strategy selection"""
        # Simple task -> optimized
        result = await orchestrator.orchestrate("What is 2+2?")
        assert result["strategy"] == "optimized"
        
        # Coding task -> persona
        result = await orchestrator.orchestrate("Write Python code")
        assert result["strategy"] in ["persona", "optimized"]
        
        # Similarity task -> vector (if enabled)
        if orchestrator.config.get('enable_vector'):
            result = await orchestrator.orchestrate(
                "Find similar documents",
                {"strategy": "vector"}
            )
            assert result["strategy"] == "vector"
    
    @pytest.mark.asyncio
    async def test_strategy_fallback_chain(self, orchestrator):
        """Test fallback chain when strategies fail"""
        with patch.object(PersonaStrategy, 'orchestrate', side_effect=Exception("Error")):
            result = await orchestrator.orchestrate(
                "Coding task",
                {"strategy": "persona"}
            )
            
            # Should fallback to optimized
            assert result["strategy"] == "optimized"
    
    @pytest.mark.asyncio
    async def test_context_preservation(self, orchestrator):
        """Test that context is preserved through orchestration"""
        context = {
            "user_id": "test123",
            "session": "abc",
            "priority": "high"
        }
        
        result = await orchestrator.orchestrate("Test task", context)
        
        assert "context" in result
        assert result["context"]["user_id"] == "test123"
        assert result["context"]["session"] == "abc"
    
    @pytest.mark.asyncio
    async def test_statistics_tracking(self, orchestrator):
        """Test statistics are properly tracked"""
        initial_stats = orchestrator.get_statistics()
        initial_count = initial_stats["total_requests"]
        
        # Make some requests
        await orchestrator.orchestrate("Task 1")
        await orchestrator.orchestrate("Task 2")
        
        final_stats = orchestrator.get_statistics()
        
        assert final_stats["total_requests"] == initial_count + 2
        assert len(final_stats["strategy_usage"]) > 0
    
    @pytest.mark.asyncio
    async def test_concurrent_orchestration(self, orchestrator):
        """Test concurrent orchestration requests"""
        tasks = [
            orchestrator.orchestrate(f"Task {i}")
            for i in range(5)
        ]
        
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 5
        assert all("strategy" in r for r in results)
        assert all("orchestrator" in r for r in results)
    
    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self, orchestrator):
        """Test comprehensive error handling"""
        # Test with None task
        result = await orchestrator.orchestrate(None)
        assert "error" in result or result["strategy"] == "optimized"
        
        # Test with empty task
        result = await orchestrator.orchestrate("")
        assert result is not None
        
        # Test with invalid strategy
        result = await orchestrator.orchestrate("Task", {"strategy": "invalid"})
        assert result["strategy"] in orchestrator.strategies.keys()
    
    def test_add_custom_strategy(self, orchestrator):
        """Test adding custom strategies"""
        class CustomStrategy(BaseStrategy):
            async def orchestrate(self, task, context):
                return {"strategy": "custom", "result": "custom result"}
            
            def get_name(self):
                return "custom"
        
        custom = CustomStrategy()
        orchestrator.add_strategy("custom", custom)
        
        assert "custom" in orchestrator.strategies
        assert orchestrator.strategies["custom"] == custom
    
    def test_remove_strategy(self, orchestrator):
        """Test removing strategies"""
        # Add a test strategy
        mock_strategy = Mock()
        mock_strategy.get_name.return_value = "test"
        orchestrator.add_strategy("test", mock_strategy)
        
        # Remove it
        orchestrator.remove_strategy("test")
        
        assert "test" not in orchestrator.strategies
    
    @pytest.mark.asyncio
    async def test_performance_tracking(self, orchestrator):
        """Test performance metrics are tracked"""
        import time
        
        start = time.time()
        result = await orchestrator.orchestrate("Test task")
        duration = time.time() - start
        
        assert "execution_time" in result
        assert isinstance(result["execution_time"], float)
        assert result["execution_time"] <= duration + 0.1  # Small margin for overhead


if __name__ == "__main__":
    pytest.main([__file__, '-v', '--cov=core.unified_orchestrator', '--cov-report=term-missing'])
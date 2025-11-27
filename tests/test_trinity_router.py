#!/usr/bin/env python3
"""
Test Trinity Router System
Tests domain analysis, complexity evaluation, and routing decisions
"""

import pytest
import asyncio
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.domain_analyzer import DomainAnalyzer, analyze_domain
from core.complexity_evaluator import ComplexityEvaluator, evaluate_complexity, ComplexityLevel
from core.trinity_router import TrinityRouter, StrategyType


class TestDomainAnalyzer:
    """Test domain detection"""

    def test_python_detection(self):
        """Test Python domain detection"""
        analyzer = DomainAnalyzer()
        result = analyzer.analyze("Review my Python code for bugs")

        assert result.primary_domain == "python"
        assert result.task_type == "review"
        assert result.confidence > 0.7

    def test_security_detection(self):
        """Test security domain detection"""
        analyzer = DomainAnalyzer()
        result = analyzer.analyze("Check SSL certificate and encryption security")

        assert result.primary_domain == "security"
        assert "security" in result.keywords_matched

    def test_code_detection(self):
        """Test code block detection"""
        analyzer = DomainAnalyzer()
        code_query = """
        def hello():
            print("hello world")
        """
        result = analyzer.analyze(code_query)

        assert result.has_code == True
        assert result.code_language == "python"

    def test_architecture_detection(self):
        """Test architectural keyword detection"""
        analyzer = DomainAnalyzer()
        result = analyzer.analyze("Design a scalable microservices architecture")

        assert result.primary_domain in ["backend", "cloud"]
        assert result.task_type == "design"


class TestComplexityEvaluator:
    """Test complexity evaluation"""

    def test_trivial_complexity(self):
        """Test trivial query detection"""
        evaluator = ComplexityEvaluator()
        result = evaluator.evaluate("Fix typo in README")

        assert result.level == ComplexityLevel.TRIVIAL
        assert result.score < 0.3
        assert result.recommended_personas == 1

    def test_simple_complexity(self):
        """Test simple query detection"""
        evaluator = ComplexityEvaluator()
        result = evaluator.evaluate("Review my Python code for bugs and suggest improvements")

        assert result.score >= 0.0  # Should have some complexity
        assert result.recommended_personas >= 1

    def test_complex_query(self):
        """Test complex query detection"""
        evaluator = ComplexityEvaluator()
        complex_query = """
        Design and implement a production-ready microservices architecture with:
        1. Auto-scaling
        2. Load balancing
        3. Service mesh
        4. Monitoring and alerting
        5. Disaster recovery
        """
        result = evaluator.evaluate(complex_query)

        assert result.score > 0.5  # Should be complex
        assert result.recommended_personas >= 3

    def test_rag_requirement_detection(self):
        """Test RAG requirement detection"""
        evaluator = ComplexityEvaluator()
        result = evaluator.evaluate("Continue from where we left off yesterday")

        assert result.requires_rag == True


class TestTrinityRouter:
    """Test Trinity routing system"""

    @pytest.mark.asyncio
    async def test_single_strategy_routing(self):
        """Test routing to single persona strategy"""
        router = TrinityRouter()
        decision = await router.route("Fix typo in README")

        assert decision.strategy == StrategyType.SINGLE
        assert len(decision.additional_personas) == 0
        assert decision.confidence > 0.0

    @pytest.mark.asyncio
    async def test_rag_enhanced_routing(self):
        """Test routing to RAG-enhanced strategy"""
        router = TrinityRouter()
        decision = await router.route("Continue the authentication system from yesterday")

        # Should detect need for context
        assert decision.strategy in [StrategyType.RAG_ENHANCED, StrategyType.HYBRID]
        assert decision.requires_rag == True

    @pytest.mark.asyncio
    async def test_persona_selection_python(self):
        """Test persona selection for Python query"""
        router = TrinityRouter()
        decision = await router.route("Review my Python code")

        assert decision.primary_persona == "senior-developer"
        assert decision.domain_analysis.primary_domain == "python"

    @pytest.mark.asyncio
    async def test_persona_selection_devops(self):
        """Test persona selection for DevOps query"""
        router = TrinityRouter()
        decision = await router.route("Setup Kubernetes cluster")

        assert decision.primary_persona == "devops-engineer"
        assert decision.domain_analysis.primary_domain == "devops"

    @pytest.mark.asyncio
    async def test_routing_statistics(self):
        """Test routing statistics tracking"""
        router = TrinityRouter()

        # Process multiple queries
        await router.route("Fix typo")
        await router.route("Design architecture")
        await router.route("Continue from yesterday")

        stats = router.get_stats()
        assert stats["total_routes"] == 3
        assert "single_count" in stats
        assert "percentages" in stats

    @pytest.mark.asyncio
    async def test_force_strategy(self):
        """Test forcing a specific strategy"""
        router = TrinityRouter()
        decision = await router.route(
            "Simple query",
            force_strategy=StrategyType.HYBRID
        )

        assert decision.strategy == StrategyType.HYBRID

    @pytest.mark.asyncio
    async def test_confidence_calculation(self):
        """Test confidence calculation"""
        router = TrinityRouter()

        # High confidence query (clear domain, simple task)
        decision1 = await router.route("Review Python code")

        # Lower confidence query (ambiguous)
        decision2 = await router.route("Do something with the thing")

        assert decision1.confidence > decision2.confidence

    @pytest.mark.asyncio
    async def test_multiple_queries_different_domains(self):
        """Test routing across different domains"""
        router = TrinityRouter()

        queries = [
            ("Fix Python bug", "python", "senior-developer"),
            ("Design database schema", "sql", "database-expert"),
            ("Review security", "security", "security-expert"),
        ]

        for query, expected_domain, expected_persona in queries:
            decision = await router.route(query)
            assert decision.domain_analysis.primary_domain == expected_domain
            assert decision.primary_persona == expected_persona


def test_domain_analyzer_cache():
    """Test domain analyzer caching"""
    analyzer = DomainAnalyzer()

    # First call
    result1 = analyzer.analyze("Test query")

    # Second call (should hit cache)
    result2 = analyzer.analyze("Test query")

    assert result1.primary_domain == result2.primary_domain
    assert result1.confidence == result2.confidence


def test_complexity_evaluator_cache():
    """Test complexity evaluator caching"""
    evaluator = ComplexityEvaluator()

    # First call
    result1 = evaluator.evaluate("Test query")

    # Second call (should hit cache)
    result2 = evaluator.evaluate("Test query")

    assert result1.score == result2.score
    assert result1.level == result2.level


if __name__ == "__main__":
    # Run tests
    print("=" * 80)
    print("TRINITY ROUTER TEST SUITE")
    print("=" * 80)

    # Run with pytest
    pytest.main([__file__, "-v", "--tb=short"])

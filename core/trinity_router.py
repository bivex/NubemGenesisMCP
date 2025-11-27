#!/usr/bin/env python3
"""
Trinity Router - Intelligent Auto-Routing System
Automatically decides between Single Persona, Swarm, or RAG-Enhanced strategies
Core of the Trinity architecture
"""

import asyncio
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.domain_analyzer import DomainAnalyzer, DomainAnalysis
from core.complexity_evaluator import ComplexityEvaluator, ComplexityAnalysis, ComplexityLevel
from core.rag_auto_integration import RAGAutoIntegration

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    """Execution strategies"""
    SINGLE = "single"           # Single persona for simple queries
    SWARM = "swarm"             # Multiple personas for complex queries
    RAG_ENHANCED = "rag_enhanced"  # Single persona + RAG context
    HYBRID = "hybrid"           # Swarm + RAG (most powerful)


@dataclass
class RoutingDecision:
    """Result of routing decision"""
    strategy: StrategyType
    primary_persona: str
    additional_personas: List[str]
    confidence: float
    reasoning: List[str]
    estimated_time_seconds: int
    requires_rag: bool
    rag_query: Optional[str]
    domain_analysis: DomainAnalysis
    complexity_analysis: ComplexityAnalysis
    metadata: Dict[str, Any]


class TrinityRouter:
    """
    Trinity Router - Core intelligent routing system

    Analyzes queries and automatically routes to optimal execution strategy:
    - SINGLE: Fast, cost-effective for simple queries
    - SWARM: Multi-persona consensus for complex queries
    - RAG_ENHANCED: Context-aware responses using memory
    - HYBRID: Full power (swarm + RAG) for critical tasks
    """

    # Persona mappings by domain
    DOMAIN_PERSONAS = {
        "python": ["senior-developer", "python-expert", "code-reviewer"],
        "javascript": ["frontend-developer", "react-specialist", "typescript-expert"],
        "backend": ["backend-developer", "api-architect", "database-expert"],
        "frontend": ["frontend-developer", "ux-designer", "css-expert"],
        "security": ["security-expert", "penetration-tester", "compliance-specialist"],
        "devops": ["devops-engineer", "kubernetes-expert", "ci-cd-specialist"],
        "cloud": ["cloud-architect", "aws-expert", "infrastructure-engineer"],
        "data-science": ["data-scientist", "ml-engineer", "statistician"],
        "sql": ["database-expert", "sql-specialist", "data-architect"],
        "product": ["product-manager", "product-strategist", "user-researcher"],
        "qa": ["qa-engineer", "test-automation-expert", "quality-analyst"],
    }

    # Default fallback persona
    DEFAULT_PERSONA = "senior-developer"

    def __init__(self, orchestrator=None, rag_system=None):
        """
        Initialize Trinity Router

        Args:
            orchestrator: Optional UnifiedOrchestrator instance
            rag_system: Optional RAG system instance (uses RAGAutoIntegration by default)
        """
        self.domain_analyzer = DomainAnalyzer()
        self.complexity_evaluator = ComplexityEvaluator()
        self.orchestrator = orchestrator

        # RAG System - use provided or create new RAGAutoIntegration
        if rag_system:
            self.rag_system = rag_system
        else:
            logger.info("   🚀 Initializing RAG Auto-Integration...")
            self.rag_system = RAGAutoIntegration()

        # Statistics
        self.stats = {
            "total_routes": 0,
            "single_count": 0,
            "swarm_count": 0,
            "rag_enhanced_count": 0,
            "hybrid_count": 0,
        }

    async def route(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        force_strategy: Optional[StrategyType] = None
    ) -> RoutingDecision:
        """
        Main routing function - analyzes query and returns optimal strategy

        Args:
            query: User query string
            context: Optional additional context
            force_strategy: Optional strategy override for testing

        Returns:
            RoutingDecision with complete routing information
        """
        logger.info(f"🎯 Trinity Router analyzing query: {query[:60]}...")

        # 1. Domain Analysis
        domain_analysis = self.domain_analyzer.analyze(query)
        logger.info(f"   Domain: {domain_analysis.primary_domain} ({domain_analysis.confidence:.2f})")

        # 2. Complexity Evaluation
        complexity_analysis = self.complexity_evaluator.evaluate(query, domain_analysis)
        logger.info(f"   Complexity: {complexity_analysis.level.value} ({complexity_analysis.score:.2f})")

        # 3. Strategy Selection (or use forced strategy)
        if force_strategy:
            strategy = force_strategy
            logger.info(f"   Strategy: {strategy.value} (FORCED)")
        else:
            strategy = self._select_strategy(
                domain_analysis,
                complexity_analysis,
                context
            )
            logger.info(f"   Strategy: {strategy.value} (AUTO-SELECTED)")

        # 4. Persona Selection
        primary_persona, additional_personas = self._select_personas(
            strategy,
            domain_analysis,
            complexity_analysis
        )
        logger.info(f"   Personas: {primary_persona} + {len(additional_personas)} others")

        # 5. RAG Requirements
        requires_rag, rag_query = self._determine_rag_requirements(
            strategy,
            query,
            complexity_analysis
        )

        # 6. Calculate Confidence
        confidence = self._calculate_confidence(
            domain_analysis.confidence,
            complexity_analysis.score,
            strategy
        )

        # 7. Generate Reasoning
        reasoning = self._generate_reasoning(
            strategy,
            domain_analysis,
            complexity_analysis,
            primary_persona,
            len(additional_personas)
        )

        # 8. Estimate Time
        estimated_time = self._estimate_execution_time(
            strategy,
            complexity_analysis.score,
            len(additional_personas) + 1
        )

        # 9. Create routing decision
        decision = RoutingDecision(
            strategy=strategy,
            primary_persona=primary_persona,
            additional_personas=additional_personas,
            confidence=confidence,
            reasoning=reasoning,
            estimated_time_seconds=estimated_time,
            requires_rag=requires_rag,
            rag_query=rag_query,
            domain_analysis=domain_analysis,
            complexity_analysis=complexity_analysis,
            metadata={
                "query_length": len(query),
                "has_code": domain_analysis.has_code,
                "code_language": domain_analysis.code_language,
                "context_provided": context is not None,
            }
        )

        # 10. Update statistics
        self._update_stats(strategy)

        logger.info(f"✅ Routing complete: {strategy.value} with {confidence:.2f} confidence")
        return decision

    def _select_strategy(
        self,
        domain_analysis: DomainAnalysis,
        complexity_analysis: ComplexityAnalysis,
        context: Optional[Dict]
    ) -> StrategyType:
        """
        Select optimal execution strategy based on analysis

        Decision Matrix:
        - Complexity < 0.3 + No RAG needed + 1 persona → SINGLE
        - Complexity < 0.3 + RAG needed → RAG_ENHANCED
        - Recommended personas >= 2 + No RAG → SWARM
        - Complexity 0.3-0.7 + No RAG → SWARM (2-3 personas)
        - Complexity 0.3-0.7 + RAG → HYBRID
        - Complexity > 0.7 → HYBRID (full power)
        """
        complexity_score = complexity_analysis.score
        requires_rag = complexity_analysis.requires_rag
        recommended_personas = complexity_analysis.recommended_personas

        # Check for explicit context requirements
        if context and context.get("force_rag"):
            requires_rag = True

        # Decision logic - Consider both complexity and recommended personas
        if complexity_score < 0.3 and recommended_personas == 1:
            # Simple queries with single persona
            if requires_rag:
                return StrategyType.RAG_ENHANCED
            else:
                return StrategyType.SINGLE
        elif recommended_personas >= 2 and not requires_rag:
            # Multiple personas recommended, no RAG needed
            return StrategyType.SWARM
        elif recommended_personas >= 2 and requires_rag:
            # Multiple personas + RAG = HYBRID
            return StrategyType.HYBRID

        elif complexity_score < 0.7:
            # Moderate complexity
            if requires_rag:
                return StrategyType.HYBRID
            else:
                return StrategyType.SWARM

        else:
            # High complexity - always hybrid
            return StrategyType.HYBRID

    def _select_personas(
        self,
        strategy: StrategyType,
        domain_analysis: DomainAnalysis,
        complexity_analysis: ComplexityAnalysis
    ) -> Tuple[str, List[str]]:
        """
        Select personas based on strategy and analysis

        Returns:
            (primary_persona, additional_personas)
        """
        # Get domain-specific personas
        domain = domain_analysis.primary_domain
        available_personas = self.DOMAIN_PERSONAS.get(domain, [self.DEFAULT_PERSONA])

        if not available_personas:
            available_personas = [self.DEFAULT_PERSONA]

        # Primary persona is always first in list
        primary_persona = available_personas[0]

        # Additional personas depend on strategy
        additional_personas = []

        if strategy in [StrategyType.SWARM, StrategyType.HYBRID]:
            # Use recommended number from complexity analysis
            num_personas = complexity_analysis.recommended_personas

            # Get additional personas (up to num_personas - 1)
            for i in range(1, min(num_personas, len(available_personas))):
                additional_personas.append(available_personas[i])

            # If we need more personas than available in domain, add general ones
            while len(additional_personas) < num_personas - 1:
                additional_personas.append("technical-architect")
                break  # Add just one general persona

        return primary_persona, additional_personas

    def _determine_rag_requirements(
        self,
        strategy: StrategyType,
        query: str,
        complexity_analysis: ComplexityAnalysis
    ) -> Tuple[bool, Optional[str]]:
        """
        Determine if RAG is needed and generate RAG query
        Uses RAG Auto-Integration for smart detection

        Returns:
            (requires_rag, rag_query)
        """
        # Strategy-based requirement
        requires_rag = strategy in [StrategyType.RAG_ENHANCED, StrategyType.HYBRID]

        # Additionally check if RAG Auto-Integration detects need for context
        if not requires_rag and self.rag_system:
            auto_detected = self.rag_system.should_use_rag(query)
            if auto_detected:
                logger.info("   🔍 RAG Auto-detected: Query needs context")
                requires_rag = True

        if not requires_rag:
            return False, None

        # Generate RAG query (simplified version of original query)
        rag_query = self._generate_rag_query(query)

        return True, rag_query

    def _generate_rag_query(self, query: str) -> str:
        """Generate optimized query for RAG search"""
        # Simple version: use first 100 chars
        # Could be enhanced with keyword extraction
        return query[:100]

    def _calculate_confidence(
        self,
        domain_confidence: float,
        complexity_score: float,
        strategy: StrategyType
    ) -> float:
        """Calculate overall routing confidence"""
        # Start with domain confidence
        confidence = domain_confidence

        # Adjust based on complexity (higher complexity = lower confidence)
        confidence *= (1.0 - complexity_score * 0.2)

        # Strategy-specific adjustments
        if strategy == StrategyType.HYBRID:
            confidence *= 1.1  # Hybrid is most comprehensive
        elif strategy == StrategyType.SINGLE:
            confidence *= 0.9  # Single persona has less validation

        # Clamp to 0-1
        return min(max(confidence, 0.0), 1.0)

    def _generate_reasoning(
        self,
        strategy: StrategyType,
        domain_analysis: DomainAnalysis,
        complexity_analysis: ComplexityAnalysis,
        primary_persona: str,
        total_personas: int
    ) -> List[str]:
        """Generate human-readable reasoning for decision"""
        reasoning = []

        # Domain reasoning
        reasoning.append(
            f"Domain detected: {domain_analysis.primary_domain} "
            f"(confidence: {domain_analysis.confidence:.2f})"
        )

        # Complexity reasoning
        reasoning.append(
            f"Complexity level: {complexity_analysis.level.value} "
            f"(score: {complexity_analysis.score:.2f})"
        )

        # Strategy reasoning
        strategy_reasons = {
            StrategyType.SINGLE: f"Simple query → Single persona ({primary_persona}) is sufficient",
            StrategyType.SWARM: f"Complex query → {total_personas} personas for diverse perspectives",
            StrategyType.RAG_ENHANCED: f"Context-dependent → Using {primary_persona} + memory",
            StrategyType.HYBRID: f"Critical task → Full power: {total_personas} personas + memory"
        }
        reasoning.append(strategy_reasons[strategy])

        # Add top complexity factors
        for reason in complexity_analysis.reasoning[:2]:
            reasoning.append(reason)

        return reasoning

    def _estimate_execution_time(
        self,
        strategy: StrategyType,
        complexity_score: float,
        num_personas: int
    ) -> int:
        """Estimate execution time in seconds"""
        # Base times by strategy
        base_times = {
            StrategyType.SINGLE: 2,
            StrategyType.SWARM: 8,
            StrategyType.RAG_ENHANCED: 4,
            StrategyType.HYBRID: 12,
        }

        base_time = base_times[strategy]

        # Adjust for complexity
        complexity_multiplier = 1 + (complexity_score * 0.5)

        # Adjust for number of personas (parallel execution)
        persona_multiplier = 1 + ((num_personas - 1) * 0.3)

        total_time = int(base_time * complexity_multiplier * persona_multiplier)

        return max(total_time, 1)

    def _update_stats(self, strategy: StrategyType):
        """Update routing statistics"""
        self.stats["total_routes"] += 1

        if strategy == StrategyType.SINGLE:
            self.stats["single_count"] += 1
        elif strategy == StrategyType.SWARM:
            self.stats["swarm_count"] += 1
        elif strategy == StrategyType.RAG_ENHANCED:
            self.stats["rag_enhanced_count"] += 1
        elif strategy == StrategyType.HYBRID:
            self.stats["hybrid_count"] += 1

    def get_stats(self) -> Dict[str, Any]:
        """Get routing statistics"""
        total = self.stats["total_routes"]
        if total == 0:
            return self.stats

        return {
            **self.stats,
            "percentages": {
                "single": (self.stats["single_count"] / total) * 100,
                "swarm": (self.stats["swarm_count"] / total) * 100,
                "rag_enhanced": (self.stats["rag_enhanced_count"] / total) * 100,
                "hybrid": (self.stats["hybrid_count"] / total) * 100,
            }
        }

    def to_dict(self, decision: RoutingDecision) -> Dict[str, Any]:
        """Convert routing decision to dictionary"""
        return {
            "strategy": decision.strategy.value,
            "primary_persona": decision.primary_persona,
            "additional_personas": decision.additional_personas,
            "confidence": decision.confidence,
            "reasoning": decision.reasoning,
            "estimated_time_seconds": decision.estimated_time_seconds,
            "requires_rag": decision.requires_rag,
            "rag_query": decision.rag_query,
            "domain": decision.domain_analysis.primary_domain,
            "complexity": decision.complexity_analysis.level.value,
            "complexity_score": decision.complexity_analysis.score,
            "metadata": decision.metadata,
        }


# Convenience function
async def route_query(
    query: str,
    context: Optional[Dict[str, Any]] = None,
    orchestrator=None,
    rag_system=None
) -> RoutingDecision:
    """Route a query (convenience async function)"""
    router = TrinityRouter(orchestrator, rag_system)
    return await router.route(query, context)


if __name__ == "__main__":
    # Test the Trinity Router
    async def test_trinity():
        test_queries = [
            "Fix typo in README",
            "Review my Python code for bugs",
            "Design a scalable microservices architecture on AWS",
            "Continue from where we left off yesterday with the authentication system",
            "Create production-ready Kubernetes deployment with auto-scaling and monitoring",
        ]

        router = TrinityRouter()

        print("=" * 80)
        print("TRINITY ROUTER TEST")
        print("=" * 80)

        for query in test_queries:
            print(f"\n{'='*80}")
            print(f"Query: {query}")
            print(f"{'='*80}")

            decision = await router.route(query)

            print(f"\nStrategy: {decision.strategy.value}")
            print(f"Confidence: {decision.confidence:.2f}")
            print(f"Primary Persona: {decision.primary_persona}")
            print(f"Additional Personas: {', '.join(decision.additional_personas) if decision.additional_personas else 'None'}")
            print(f"Requires RAG: {decision.requires_rag}")
            print(f"Estimated Time: {decision.estimated_time_seconds}s")
            print(f"\nReasoning:")
            for reason in decision.reasoning:
                print(f"  • {reason}")

        # Print statistics
        print(f"\n{'='*80}")
        print("ROUTING STATISTICS")
        print(f"{'='*80}")
        stats = router.get_stats()
        print(f"Total routes: {stats['total_routes']}")
        if 'percentages' in stats:
            print(f"Single: {stats['percentages']['single']:.1f}%")
            print(f"Swarm: {stats['percentages']['swarm']:.1f}%")
            print(f"RAG Enhanced: {stats['percentages']['rag_enhanced']:.1f}%")
            print(f"Hybrid: {stats['percentages']['hybrid']:.1f}%")

    # Run test
    asyncio.run(test_trinity())

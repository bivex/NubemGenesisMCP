#!/usr/bin/env python3
"""
Master Persona Router - Unified integration of all advanced routing components
===============================================================================

This is the main entry point that integrates:
1. Semantic Embedding Matching
2. Reinforcement Learning Router
3. Ensemble Routing
4. A/B Testing Framework
5. Comprehensive Metrics

Author: NubemSuperFClaude Team
Date: 2025-10-12
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Import all routing components
from .advanced_persona_router import (
    RoutingContext,
    RoutingResult,
    FeedbackRecord,
    SemanticMatcher,
    RLPersonaRouter,
    EnsembleRouter
)

from .advanced_persona_router_pt2 import (
    ABTestVariant,
    ABTestResult,
    ABTestManager,
    RoutingMetricsCollector
)

# Import persona system
from .personas_unified import UnifiedPersonaManager

logger = logging.getLogger(__name__)


class MasterPersonaRouter:
    """
    Master orchestrator integrating all advanced routing capabilities

    Features:
    - Multi-strategy routing (semantic, RL, ensemble)
    - Real-time A/B testing
    - Comprehensive metrics and monitoring
    - Learning from user feedback
    - Production-ready with persistence
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Master Persona Router

        Args:
            config: Configuration dictionary with optional parameters:
                - enable_semantic: Enable semantic matching (default: True)
                - enable_rl: Enable reinforcement learning (default: True)
                - enable_ensemble: Enable ensemble routing (default: True)
                - enable_ab_testing: Enable A/B testing (default: True)
                - data_dir: Directory for persistence (default: ./data/routing)
                - embedding_model: Sentence transformer model (default: all-MiniLM-L6-v2)
        """
        self.config = config or {}
        self.data_dir = Path(self.config.get('data_dir', './data/routing'))
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Initialize persona manager
        self.persona_manager = UnifiedPersonaManager()
        self.available_personas = list(self.persona_manager.personas.keys())

        logger.info(f"Loaded {len(self.available_personas)} personas for routing")

        # Initialize components
        self._initialize_components()

        # Statistics
        self.session_start = datetime.now()
        self.routing_cache: Dict[str, RoutingResult] = {}

        logger.info("✅ MasterPersonaRouter initialized successfully")

    def _initialize_components(self):
        """Initialize all routing components"""

        # 1. Semantic Matcher
        if self.config.get('enable_semantic', True):
            model_name = self.config.get('embedding_model', 'all-MiniLM-L6-v2')
            self.semantic_matcher = SemanticMatcher(model_name=model_name)
            logger.info("✅ Semantic matcher initialized")
        else:
            self.semantic_matcher = None

        # 2. RL Router
        if self.config.get('enable_rl', True):
            self.rl_router = RLPersonaRouter(
                learning_rate=self.config.get('rl_learning_rate', 0.1),
                discount_factor=self.config.get('rl_discount', 0.9),
                exploration_rate=self.config.get('rl_exploration', 0.1)
            )
            # Load existing model
            rl_model_path = self.data_dir / 'rl_model.json'
            if rl_model_path.exists():
                self.rl_router.load_model(str(rl_model_path))
            logger.info("✅ RL router initialized")
        else:
            self.rl_router = None

        # 3. Ensemble Router
        if self.config.get('enable_ensemble', True):
            self.ensemble_router = EnsembleRouter()

            # Add strategies to ensemble
            if self.semantic_matcher:
                self.ensemble_router.add_strategy(
                    'semantic',
                    self.semantic_matcher,
                    weight=1.0
                )
            if self.rl_router:
                self.ensemble_router.add_strategy(
                    'reinforcement_learning',
                    self.rl_router,
                    weight=0.8  # Slightly lower initially
                )

            logger.info("✅ Ensemble router initialized")
        else:
            self.ensemble_router = None

        # 4. A/B Testing
        if self.config.get('enable_ab_testing', True):
            ab_test_path = self.data_dir / 'ab_tests.json'
            self.ab_test_manager = ABTestManager(
                persistence_path=str(ab_test_path)
            )
            logger.info("✅ A/B testing framework initialized")
        else:
            self.ab_test_manager = None

        # 5. Metrics Collector
        self.metrics_collector = RoutingMetricsCollector(
            persistence_path=str(self.data_dir / 'metrics.json')
        )
        logger.info("✅ Metrics collector initialized")

    async def route(self,
                   task: str,
                   context: Optional[Dict[str, Any]] = None,
                   strategy: str = 'auto',
                   session_id: Optional[str] = None) -> RoutingResult:
        """
        Main routing method - selects best persona for task

        Args:
            task: Task description
            context: Additional context (domains, complexity, history, etc.)
            strategy: Routing strategy ('auto', 'semantic', 'rl', 'ensemble')
            session_id: Session identifier for A/B testing

        Returns:
            RoutingResult with selected persona and metadata
        """
        start_time = time.time()
        routing_id = str(uuid.uuid4())

        # Build routing context
        routing_context = self._build_routing_context(task, context, session_id)

        # Check A/B test assignment
        ab_variant = None
        if self.ab_test_manager and session_id:
            ab_variant = self._check_ab_test(session_id)
            if ab_variant:
                strategy = ab_variant.routing_strategy
                logger.debug(f"A/B test: using variant {ab_variant.variant_id} with strategy {strategy}")

        # Select routing strategy
        if strategy == 'auto':
            strategy = self._auto_select_strategy(routing_context)

        # Execute routing
        try:
            if strategy == 'semantic' and self.semantic_matcher:
                result = await self._route_semantic(routing_context)
            elif strategy == 'rl' and self.rl_router:
                result = await self._route_rl(routing_context)
            elif strategy == 'ensemble' and self.ensemble_router:
                result = await self._route_ensemble(routing_context)
            else:
                # Fallback to simple rule-based routing
                result = await self._route_fallback(routing_context)

            result.strategy_used = strategy
            result.routing_time_ms = (time.time() - start_time) * 1000
            result.ab_test_variant = ab_variant.variant_id if ab_variant else None

            # Record metrics
            self.metrics_collector.record_routing(
                result,
                routing_context,
                success=True,
                user_rating=None  # Will be updated with feedback
            )

            # Cache result
            self.routing_cache[routing_id] = result

            return result

        except Exception as e:
            logger.error(f"Routing failed: {e}", exc_info=True)
            # Return fallback result
            return RoutingResult(
                primary_persona='architect',  # Safe default
                support_personas=[],
                confidence_score=0.3,
                strategy_used='fallback',
                routing_time_ms=(time.time() - start_time) * 1000,
                reasoning=f"Error during routing: {str(e)}"
            )

    def _build_routing_context(self,
                               task: str,
                               context: Optional[Dict],
                               session_id: Optional[str]) -> RoutingContext:
        """Build comprehensive routing context"""
        ctx = context or {}

        return RoutingContext(
            task=task,
            task_type=ctx.get('task_type'),
            domains=set(ctx.get('domains', [])),
            complexity_level=ctx.get('complexity', 0.5),
            required_capabilities=set(ctx.get('capabilities', [])),
            conversation_history=ctx.get('history', []),
            user_preferences=ctx.get('preferences', {}),
            session_id=session_id
        )

    def _check_ab_test(self, session_id: str) -> Optional[ABTestVariant]:
        """Check if user is in an active A/B test"""
        if not self.ab_test_manager:
            return None

        # Check all active tests (simplified - assumes one test)
        # In production, would have test prioritization
        active_tests = list(self.ab_test_manager.active_tests.keys())
        if not active_tests:
            return None

        test_id = active_tests[0]  # Use first active test
        return self.ab_test_manager.assign_variant(test_id, session_id)

    def _auto_select_strategy(self, context: RoutingContext) -> str:
        """Automatically select best routing strategy"""

        # Use ensemble if available (best quality)
        if self.ensemble_router:
            return 'ensemble'

        # Use RL if we have enough training data
        if self.rl_router and self.rl_router.total_updates > 100:
            return 'rl'

        # Use semantic matching as default
        if self.semantic_matcher:
            return 'semantic'

        return 'fallback'

    async def _route_semantic(self, context: RoutingContext) -> RoutingResult:
        """Route using semantic similarity"""
        # Build persona descriptions for matching
        persona_descriptions = {}
        for persona_id in self.available_personas:
            persona = self.persona_manager.personas[persona_id]
            # Combine identity and specialties for rich description
            desc = f"{persona.identity}. Specialties: {', '.join(persona.specialties[:10])}"
            persona_descriptions[persona_id] = desc

        # Find best matches
        matches = self.semantic_matcher.find_best_matches(
            context.task,
            persona_descriptions,
            top_k=5
        )

        if not matches:
            return RoutingResult(
                primary_persona='architect',
                support_personas=[],
                confidence_score=0.3,
                strategy_used='semantic',
                routing_time_ms=0
            )

        primary = matches[0]
        support = [m[0] for m in matches[1:3]]  # Top 2-4 as support

        return RoutingResult(
            primary_persona=primary[0],
            support_personas=support,
            confidence_score=float(primary[1]),
            strategy_used='semantic',
            routing_time_ms=0,
            embedding_similarity=float(primary[1]),
            all_scores={m[0]: m[1] for m in matches},
            reasoning=f"Semantic match: {primary[1]:.2%} similarity"
        )

    async def _route_rl(self, context: RoutingContext) -> RoutingResult:
        """Route using reinforcement learning"""
        persona, q_value = self.rl_router.select_persona(
            context,
            self.available_personas,
            exploit_only=False
        )

        # Get support personas from semantic similarity if available
        support = []
        if self.semantic_matcher:
            semantic_result = await self._route_semantic(context)
            support = [p for p in semantic_result.support_personas
                      if p != persona][:2]

        return RoutingResult(
            primary_persona=persona,
            support_personas=support,
            confidence_score=min(abs(q_value), 1.0),
            strategy_used='rl',
            routing_time_ms=0,
            reasoning=f"RL Q-value: {q_value:.3f}"
        )

    async def _route_ensemble(self, context: RoutingContext) -> RoutingResult:
        """Route using ensemble method"""
        ensemble_method = self.config.get('ensemble_method', 'weighted_voting')

        persona, metadata = self.ensemble_router.select_persona(
            context,
            self.available_personas,
            method=ensemble_method
        )

        # Extract support personas from ensemble results
        support = []
        if 'all_votes' in metadata:
            sorted_votes = sorted(
                metadata['all_votes'].items(),
                key=lambda x: x[1],
                reverse=True
            )
            support = [p for p, _ in sorted_votes[1:3] if p != persona]

        return RoutingResult(
            primary_persona=persona,
            support_personas=support,
            confidence_score=metadata.get('winning_score', 0.7),
            strategy_used='ensemble',
            routing_time_ms=0,
            all_scores=metadata.get('all_votes', {}),
            reasoning=f"Ensemble ({ensemble_method}): {metadata.get('winning_score', 0):.3f}"
        )

    async def _route_fallback(self, context: RoutingContext) -> RoutingResult:
        """Simple rule-based fallback routing"""
        task_lower = context.task.lower()

        # Simple keyword matching
        persona_map = {
            'architect': ['architecture', 'design', 'system', 'scalability'],
            'frontend': ['ui', 'ux', 'react', 'vue', 'angular', 'css', 'html'],
            'backend': ['api', 'server', 'database', 'rest', 'graphql'],
            'security-analyst': ['security', 'vulnerability', 'encrypt', 'auth'],
            'devops-engineer': ['deploy', 'ci/cd', 'docker', 'kubernetes'],
            'data-engineer': ['data', 'etl', 'pipeline', 'analytics'],
        }

        best_match = 'architect'  # Default
        best_score = 0

        for persona, keywords in persona_map.items():
            if persona not in self.available_personas:
                continue
            score = sum(1 for kw in keywords if kw in task_lower)
            if score > best_score:
                best_score = score
                best_match = persona

        return RoutingResult(
            primary_persona=best_match,
            support_personas=[],
            confidence_score=0.5,
            strategy_used='fallback',
            routing_time_ms=0,
            reasoning="Rule-based fallback routing"
        )

    def provide_feedback(self,
                        routing_id: str,
                        user_rating: float,
                        success: bool,
                        session_id: Optional[str] = None):
        """
        Provide feedback for a routing decision (enables learning)

        Args:
            routing_id: ID from routing result
            user_rating: User rating (0.0-1.0)
            success: Whether the routing was successful
            session_id: Session ID for A/B testing
        """
        if routing_id not in self.routing_cache:
            logger.warning(f"Routing ID {routing_id} not found in cache")
            return

        result = self.routing_cache[routing_id]

        # Update RL router
        if self.rl_router:
            feedback = FeedbackRecord(
                routing_id=routing_id,
                persona_selected=result.primary_persona,
                task_context=f"{result.strategy_used}:confidence_{result.confidence_score:.2f}",
                user_rating=user_rating,
                success=success,
                latency_ms=result.routing_time_ms
            )
            self.rl_router.update_from_feedback(feedback)

        # Update ensemble weights
        if self.ensemble_router:
            performance_score = (user_rating + (1.0 if success else 0.0)) / 2.0
            self.ensemble_router.update_weights(result.strategy_used, performance_score)

        # Record A/B test result
        if self.ab_test_manager and result.ab_test_variant and session_id:
            # Find test ID (simplified)
            for test_id in self.ab_test_manager.active_tests.keys():
                ab_result = ABTestResult(
                    test_id=test_id,
                    variant_id=result.ab_test_variant,
                    persona_selected=result.primary_persona,
                    success=success,
                    user_rating=user_rating,
                    latency_ms=result.routing_time_ms,
                    session_id=session_id
                )
                self.ab_test_manager.record_result(ab_result)

        logger.info(f"Feedback recorded: rating={user_rating:.2f}, success={success}")

    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive routing metrics"""
        metrics = {
            'summary': self.metrics_collector.get_summary(),
            'insights': self.metrics_collector.get_insights(),
        }

        if self.rl_router:
            metrics['rl_stats'] = self.rl_router.get_statistics()

        if self.ensemble_router:
            metrics['ensemble_stats'] = self.ensemble_router.get_statistics()

        if self.semantic_matcher:
            metrics['cache_stats'] = self.semantic_matcher.get_cache_stats()

        return metrics

    def create_ab_test(self,
                      test_name: str,
                      variants: List[Tuple[str, str, float]]) -> bool:
        """
        Create new A/B test

        Args:
            test_name: Test identifier
            variants: List of (variant_name, strategy, traffic_allocation)

        Returns:
            Success status
        """
        if not self.ab_test_manager:
            logger.warning("A/B testing not enabled")
            return False

        variant_objects = [
            ABTestVariant(
                variant_id=f"{test_name}_{name}",
                name=name,
                description=f"Using {strategy} routing strategy",
                routing_strategy=strategy,
                strategy_params={},
                traffic_allocation=allocation,
                is_control=(i == 0)
            )
            for i, (name, strategy, allocation) in enumerate(variants)
        ]

        return self.ab_test_manager.create_test(test_name, variant_objects)

    def get_ab_test_results(self, test_name: str) -> Dict[str, Any]:
        """Get A/B test results"""
        if not self.ab_test_manager:
            return {'error': 'A/B testing not enabled'}

        return self.ab_test_manager.get_test_statistics(test_name)

    def save_state(self):
        """Save all router state to disk"""
        if self.rl_router:
            rl_path = self.data_dir / 'rl_model.json'
            self.rl_router.save_model(str(rl_path))

        if self.ab_test_manager:
            self.ab_test_manager.save_state()

        if self.metrics_collector:
            metrics_path = self.data_dir / 'metrics_export.json'
            self.metrics_collector.export_to_file(str(metrics_path))

        logger.info("Router state saved successfully")

    def __del__(self):
        """Cleanup: save state on destruction"""
        try:
            self.save_state()
        except:
            pass


# ============================================================================
# Convenience functions
# ============================================================================

_global_router: Optional[MasterPersonaRouter] = None


def get_master_router(config: Optional[Dict[str, Any]] = None) -> MasterPersonaRouter:
    """Get or create global master router instance"""
    global _global_router
    if _global_router is None:
        _global_router = MasterPersonaRouter(config)
    return _global_router


async def route_task(task: str, **kwargs) -> RoutingResult:
    """Convenience function to route a task"""
    router = get_master_router()
    return await router.route(task, **kwargs)


# ============================================================================
# Example usage
# ============================================================================

async def demo():
    """Demonstrate master router capabilities"""
    print("="*80)
    print("🚀 Master Persona Router Demo")
    print("="*80)

    # Initialize router
    router = MasterPersonaRouter({
        'enable_semantic': True,
        'enable_rl': True,
        'enable_ensemble': True,
        'enable_ab_testing': True,
        'data_dir': './data/routing_demo'
    })

    # Test routing
    test_tasks = [
        "Design a microservices architecture for e-commerce platform",
        "Create a React dashboard with real-time charts",
        "Implement REST API for user management with JWT auth",
        "Set up CI/CD pipeline with Docker and Kubernetes",
        "Analyze customer behavior data and create ML model"
    ]

    print(f"\n📊 Testing routing with {len(test_tasks)} tasks...\n")

    for i, task in enumerate(test_tasks, 1):
        print(f"\n[Task {i}] {task}")
        print("-" * 80)

        # Route with different strategies
        for strategy in ['semantic', 'ensemble', 'auto']:
            result = await router.route(task, strategy=strategy, session_id=f"demo_session_{i}")

            print(f"\n  Strategy: {strategy.upper()}")
            print(f"  ✅ Primary: {result.primary_persona}")
            print(f"  🤝 Support: {', '.join(result.support_personas) if result.support_personas else 'None'}")
            print(f"  📈 Confidence: {result.confidence_score:.2%}")
            print(f"  ⏱️  Latency: {result.routing_time_ms:.1f}ms")
            print(f"  💡 Reasoning: {result.reasoning}")

            # Simulate feedback
            router.provide_feedback(
                routing_id=str(uuid.uuid4()),
                user_rating=0.85,
                success=True,
                session_id=f"demo_session_{i}"
            )

    # Show metrics
    print("\n" + "="*80)
    print("📊 Routing Metrics Summary")
    print("="*80)

    metrics = router.get_metrics()
    print(json.dumps(metrics['summary']['overview'], indent=2))

    print("\n💡 Insights:")
    for insight in metrics['insights']:
        print(f"  {insight}")

    # Save state
    router.save_state()
    print("\n✅ Demo complete! State saved.")


if __name__ == "__main__":
    import json
    asyncio.run(demo())

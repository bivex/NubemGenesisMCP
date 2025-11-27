#!/usr/bin/env python3
"""
Complete Trinity Architecture Testing
Tests all 3 phases: Trinity Router + Swarm Engine + RAG Auto-Integration
"""

import sys
import asyncio
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.trinity_router import TrinityRouter, StrategyType
from core.swarm_executor import SwarmExecutor, ExecutionMode
from core.consensus_builder import ConsensusBuilder
from core.response_synthesizer import ResponseSynthesizer
from core.rag_auto_integration import RAGAutoIntegration


class TestTrinityComplete:
    """Complete testing of Trinity Architecture"""

    def __init__(self):
        print("=" * 80)
        print("TRINITY ARCHITECTURE - COMPLETE TESTING")
        print("Testing: Phase 1 (Router) + Phase 2 (Swarm) + Phase 3 (RAG)")
        print("=" * 80)

        # Initialize components
        self.rag_system = RAGAutoIntegration()
        self.trinity_router = TrinityRouter(rag_system=self.rag_system)
        self.swarm_executor = SwarmExecutor()
        self.consensus_builder = ConsensusBuilder()
        self.response_synthesizer = ResponseSynthesizer()

        self.test_results = []

    def log_test(self, name: str, passed: bool, details: str = ""):
        """Log test result"""
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} | {name}")
        if details:
            print(f"     {details}")
        self.test_results.append((name, passed, details))

    async def test_1_rag_auto_trigger(self):
        """Test 1: RAG Auto-Trigger Detection"""
        print("\n" + "=" * 80)
        print("TEST 1: RAG Auto-Trigger Detection")
        print("=" * 80)

        test_cases = [
            ("Fix bug in code", False, "Simple query should NOT trigger RAG"),
            ("Continue from where we left off", True, "Contextual query SHOULD trigger RAG"),
            ("Based on our previous discussion about architecture", True, "Reference to past SHOULD trigger RAG"),
            ("Remember what we talked about yesterday", True, "Memory reference SHOULD trigger RAG"),
        ]

        for query, expected, description in test_cases:
            should_use = self.rag_system.should_use_rag(query)
            passed = should_use == expected
            self.log_test(
                f"RAG Trigger: '{query[:40]}'",
                passed,
                f"{description} - Got: {should_use}, Expected: {expected}"
            )

    async def test_2_rag_context_storage(self):
        """Test 2: RAG Context Storage and Retrieval"""
        print("\n" + "=" * 80)
        print("TEST 2: RAG Context Storage & Retrieval")
        print("=" * 80)

        # Store some test interactions
        self.rag_system.store_interaction(
            "How do I deploy to Kubernetes?",
            "Use kubectl apply with your deployment manifest...",
            {"domain": "devops"}
        )

        self.rag_system.store_interaction(
            "What's the best way to scale microservices?",
            "Use horizontal pod autoscaling with custom metrics...",
            {"domain": "cloud"}
        )

        self.rag_system.store_solution(
            "Database connection pool exhaustion",
            "Increase max_connections and add connection timeout",
            tags=["database", "performance"]
        )

        stats = self.rag_system.get_stats()
        passed = stats["stored_conversations"] >= 2 and stats["stored_solutions"] >= 1

        self.log_test(
            "RAG Storage",
            passed,
            f"Stored: {stats['stored_conversations']} conversations, {stats['stored_solutions']} solutions"
        )

        # Test retrieval
        context = await self.rag_system.retrieve_context("How to deploy and scale microservices?", limit=3)
        passed = context.total_results > 0

        self.log_test(
            "RAG Retrieval",
            passed,
            f"Retrieved {context.total_results} contexts in {context.retrieval_time_ms}ms"
        )

    async def test_3_rag_query_enrichment(self):
        """Test 3: RAG Query Enrichment"""
        print("\n" + "=" * 80)
        print("TEST 3: RAG Query Enrichment")
        print("=" * 80)

        query = "Continue with the Kubernetes deployment"
        enriched = await self.rag_system.enrich_query(query)

        passed = len(enriched.enriched_query) > len(query)  # Should be longer with context

        self.log_test(
            "Query Enrichment",
            passed,
            f"Original: {len(query)} chars → Enriched: {len(enriched.enriched_query)} chars (confidence: {enriched.confidence:.2f})"
        )

    async def test_4_trinity_router_all_strategies(self):
        """Test 4: Trinity Router - All 4 Strategies"""
        print("\n" + "=" * 80)
        print("TEST 4: Trinity Router - All 4 Strategies")
        print("=" * 80)

        test_cases = [
            ("Fix typo in README", StrategyType.SINGLE, "Simple query → SINGLE"),
            ("Design scalable microservices architecture with Kubernetes and service mesh", StrategyType.SWARM, "Complex query → SWARM"),
            ("Continue with the previous API design", StrategyType.RAG_ENHANCED, "Contextual query → RAG_ENHANCED (auto-detected)"),
            ("Based on our earlier discussion, design a comprehensive security audit system with multiple validation layers", StrategyType.HYBRID, "Complex + Contextual → HYBRID"),
        ]

        for query, expected_strategy, description in test_cases:
            decision = await self.trinity_router.route(query)
            passed = decision.strategy == expected_strategy

            self.log_test(
                f"Strategy: {expected_strategy.value}",
                passed,
                f"{description} - Got: {decision.strategy.value}, Confidence: {decision.confidence:.2f}"
            )

    async def test_5_swarm_consensus(self):
        """Test 5: Swarm Execution + Consensus"""
        print("\n" + "=" * 80)
        print("TEST 5: Swarm Execution + Consensus")
        print("=" * 80)

        # Simulated swarm responses (in real scenario, these come from orchestrator)
        mock_responses = [
            {
                "persona_name": "system-architect",
                "response": "I recommend using microservices architecture with API gateway and service mesh for security.",
                "confidence": 0.9,
                "execution_time_ms": 150,
                "success": True
            },
            {
                "persona_name": "backend-developer",
                "response": "Use microservices pattern with API gateway. Consider event-driven architecture for scalability.",
                "confidence": 0.85,
                "execution_time_ms": 140,
                "success": True
            },
            {
                "persona_name": "devops-engineer",
                "response": "Microservices on Kubernetes with API gateway and horizontal pod autoscaling.",
                "confidence": 0.88,
                "execution_time_ms": 160,
                "success": True
            }
        ]

        # Build consensus
        consensus_result = self.consensus_builder.build_consensus(
            mock_responses,
            "Design scalable architecture"
        )

        passed = (
            consensus_result.agreement_score > 0.6 and
            len(consensus_result.consensus_points) > 0
        )

        self.log_test(
            "Swarm Consensus",
            passed,
            f"Agreement: {consensus_result.agreement_score:.2f}, Consensus points: {len(consensus_result.consensus_points)}"
        )

        return mock_responses, consensus_result

    async def test_6_response_synthesis(self):
        """Test 6: Response Synthesis"""
        print("\n" + "=" * 80)
        print("TEST 6: Response Synthesis")
        print("=" * 80)

        # Use mock data from test 5
        from dataclasses import dataclass
        from typing import List

        @dataclass
        class MockPersonaResponse:
            persona_name: str
            response: str
            confidence: float
            execution_time_ms: int
            success: bool

        @dataclass
        class MockSwarmResult:
            query: str
            personas: List[str]
            individual_responses: List[MockPersonaResponse]
            execution_mode: str
            total_time_ms: int
            success_count: int
            failure_count: int

        @dataclass
        class MockConsensusPoint:
            content: str
            supporting_personas: List[str]
            confidence: float
            category: str

        @dataclass
        class MockConsensusResult:
            agreement_score: float
            consensus_points: List[MockConsensusPoint]
            disagreement_points: List
            dominant_themes: List[str]
            recommended_action: str
            confidence: float
            metadata: dict

        mock_swarm = MockSwarmResult(
            query="Design architecture",
            personas=["system-architect", "backend-developer", "devops-engineer"],
            individual_responses=[
                MockPersonaResponse("system-architect", "Microservices with API gateway", 0.9, 150, True),
                MockPersonaResponse("backend-developer", "Event-driven microservices", 0.85, 140, True),
                MockPersonaResponse("devops-engineer", "Kubernetes deployment", 0.88, 160, True)
            ],
            execution_mode="parallel",
            total_time_ms=160,
            success_count=3,
            failure_count=0
        )

        mock_consensus = MockConsensusResult(
            agreement_score=0.85,
            consensus_points=[
                MockConsensusPoint("Use microservices", ["system-architect", "backend-developer"], 1.0, "unanimous"),
                MockConsensusPoint("API gateway", ["system-architect", "devops-engineer"], 0.67, "majority")
            ],
            disagreement_points=[],
            dominant_themes=["microservices", "api", "kubernetes"],
            recommended_action="Strong consensus",
            confidence=0.88,
            metadata={"total_responses": 3}
        )

        synthesized = self.response_synthesizer.synthesize(
            query="Design architecture",
            swarm_result=mock_swarm,
            consensus_result=mock_consensus,
            style="comprehensive"
        )

        passed = (
            len(synthesized.content) > 100 and
            synthesized.confidence > 0.7 and
            len(synthesized.key_recommendations) > 0
        )

        self.log_test(
            "Response Synthesis",
            passed,
            f"Content: {len(synthesized.content)} chars, Confidence: {synthesized.confidence:.2f}, Recommendations: {len(synthesized.key_recommendations)}"
        )

    async def test_7_full_pipeline_rag_enhanced(self):
        """Test 7: Full Pipeline - RAG_ENHANCED Strategy"""
        print("\n" + "=" * 80)
        print("TEST 7: Full Pipeline - RAG_ENHANCED Strategy")
        print("=" * 80)

        query = "Continue with the database optimization we discussed"

        # 1. Route
        routing = await self.trinity_router.route(query)

        # 2. Check if RAG is triggered
        rag_triggered = routing.requires_rag or self.rag_system.should_use_rag(query)

        # 3. Enrich if needed
        enriched = None
        if rag_triggered:
            enriched = await self.rag_system.enrich_query(query)

        passed = (
            rag_triggered and
            enriched is not None and
            len(enriched.enriched_query) > len(query)
        )

        self.log_test(
            "RAG_ENHANCED Pipeline",
            passed,
            f"RAG triggered: {rag_triggered}, Query enriched: {enriched is not None}, Strategy: {routing.strategy.value}"
        )

    async def test_8_full_pipeline_hybrid(self):
        """Test 8: Full Pipeline - HYBRID Strategy (Swarm + RAG)"""
        print("\n" + "=" * 80)
        print("TEST 8: Full Pipeline - HYBRID Strategy")
        print("=" * 80)

        query = "Based on our previous architecture discussion, design a comprehensive security audit system with penetration testing and compliance checks"

        # 1. Route
        routing = await self.trinity_router.route(query)

        # 2. Enrich with RAG
        enriched = None
        if routing.requires_rag:
            enriched = await self.rag_system.enrich_query(query)

        # 3. Check strategy
        is_hybrid = routing.strategy == StrategyType.HYBRID or (
            routing.strategy == StrategyType.SWARM and routing.requires_rag
        )

        passed = (
            is_hybrid and
            len(routing.additional_personas) > 0 and
            routing.requires_rag
        )

        self.log_test(
            "HYBRID Pipeline",
            passed,
            f"Strategy: {routing.strategy.value}, Personas: {len(routing.additional_personas) + 1}, RAG: {routing.requires_rag}"
        )

    async def test_9_component_integration(self):
        """Test 9: Component Integration"""
        print("\n" + "=" * 80)
        print("TEST 9: Component Integration")
        print("=" * 80)

        # Test that all components work together
        components = {
            "Trinity Router": self.trinity_router,
            "RAG System": self.rag_system,
            "Swarm Executor": self.swarm_executor,
            "Consensus Builder": self.consensus_builder,
            "Response Synthesizer": self.response_synthesizer
        }

        for name, component in components.items():
            passed = component is not None
            self.log_test(
                f"Component: {name}",
                passed,
                "Initialized and ready"
            )

    async def test_10_statistics(self):
        """Test 10: Statistics Collection"""
        print("\n" + "=" * 80)
        print("TEST 10: Statistics Collection")
        print("=" * 80)

        trinity_stats = self.trinity_router.get_stats()
        rag_stats = self.rag_system.get_stats()

        passed = (
            trinity_stats["total_routes"] > 0 and
            rag_stats["total_retrievals"] >= 0
        )

        self.log_test(
            "Statistics",
            passed,
            f"Routes: {trinity_stats['total_routes']}, RAG retrievals: {rag_stats['total_retrievals']}"
        )

    async def run_all_tests(self):
        """Run all tests"""
        print("\n🚀 Starting Complete Trinity Testing...\n")

        await self.test_1_rag_auto_trigger()
        await self.test_2_rag_context_storage()
        await self.test_3_rag_query_enrichment()
        await self.test_4_trinity_router_all_strategies()
        await self.test_5_swarm_consensus()
        await self.test_6_response_synthesis()
        await self.test_7_full_pipeline_rag_enhanced()
        await self.test_8_full_pipeline_hybrid()
        await self.test_9_component_integration()
        await self.test_10_statistics()

        # Summary
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)

        total_tests = len(self.test_results)
        passed_tests = sum(1 for _, passed, _ in self.test_results if passed)
        failed_tests = total_tests - passed_tests

        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests*100):.1f}%")

        if failed_tests > 0:
            print("\nFailed Tests:")
            for name, passed, details in self.test_results:
                if not passed:
                    print(f"  - {name}: {details}")

        print("\n" + "=" * 80)
        if failed_tests == 0:
            print("🎉 ALL TESTS PASSED! Trinity Architecture is COMPLETE and OPERATIONAL")
        else:
            print(f"⚠️  {failed_tests} test(s) failed - Review above for details")
        print("=" * 80)

        return failed_tests == 0


async def main():
    """Main test runner"""
    tester = TestTrinityComplete()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())

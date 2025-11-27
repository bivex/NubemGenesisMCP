#!/usr/bin/env python3
"""
Swarm Executor - Parallel Multi-Persona Execution Engine
Executes queries with multiple personas in parallel and coordinates results
"""

import asyncio
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ExecutionMode(Enum):
    """Execution modes for swarm"""
    PARALLEL = "parallel"       # All personas execute simultaneously
    SEQUENTIAL = "sequential"   # Personas execute one after another
    HYBRID = "hybrid"          # Leader + parallel followers


@dataclass
class PersonaResponse:
    """Response from a single persona"""
    persona_name: str
    response: str
    confidence: float
    execution_time_ms: int
    success: bool
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SwarmResult:
    """Result from swarm execution"""
    query: str
    personas: List[str]
    individual_responses: List[PersonaResponse]
    execution_mode: ExecutionMode
    total_time_ms: int
    success_count: int
    failure_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class SwarmExecutor:
    """
    Swarm Executor - Coordinates multiple personas for complex queries

    Features:
    - Parallel execution of multiple personas
    - Error handling and fallbacks
    - Performance monitoring
    - Flexible execution modes
    """

    def __init__(self, orchestrator=None, max_concurrent=5):
        """
        Initialize Swarm Executor

        Args:
            orchestrator: Optional UnifiedOrchestrator instance
            max_concurrent: Maximum concurrent persona executions
        """
        self.orchestrator = orchestrator
        self.max_concurrent = max_concurrent
        self.execution_stats = {
            "total_swarms": 0,
            "total_personas_executed": 0,
            "average_time_ms": 0,
            "success_rate": 0.0
        }

    async def execute_swarm(
        self,
        query: str,
        personas: List[str],
        mode: ExecutionMode = ExecutionMode.PARALLEL,
        context: Optional[Dict[str, Any]] = None
    ) -> SwarmResult:
        """
        Execute query with multiple personas (swarm)

        Args:
            query: Query to process
            personas: List of persona identifiers
            mode: Execution mode (parallel, sequential, hybrid)
            context: Optional additional context

        Returns:
            SwarmResult with all persona responses
        """
        logger.info(f"🐝 Swarm executing with {len(personas)} personas: {', '.join(personas)}")
        logger.info(f"   Mode: {mode.value}")

        start_time = time.time()

        # Execute based on mode
        if mode == ExecutionMode.PARALLEL:
            individual_responses = await self._execute_parallel(query, personas, context)
        elif mode == ExecutionMode.SEQUENTIAL:
            individual_responses = await self._execute_sequential(query, personas, context)
        elif mode == ExecutionMode.HYBRID:
            individual_responses = await self._execute_hybrid(query, personas, context)
        else:
            raise ValueError(f"Unknown execution mode: {mode}")

        total_time_ms = int((time.time() - start_time) * 1000)

        # Count successes and failures
        success_count = sum(1 for r in individual_responses if r.success)
        failure_count = len(individual_responses) - success_count

        # Create result
        result = SwarmResult(
            query=query,
            personas=personas,
            individual_responses=individual_responses,
            execution_mode=mode,
            total_time_ms=total_time_ms,
            success_count=success_count,
            failure_count=failure_count,
            metadata={
                "query_length": len(query),
                "personas_count": len(personas),
                "context_provided": context is not None
            }
        )

        # Update statistics
        self._update_stats(result)

        logger.info(f"✅ Swarm complete: {success_count}/{len(personas)} successful in {total_time_ms}ms")

        return result

    async def _execute_parallel(
        self,
        query: str,
        personas: List[str],
        context: Optional[Dict]
    ) -> List[PersonaResponse]:
        """Execute all personas in parallel"""
        logger.info(f"   → Executing {len(personas)} personas in PARALLEL")

        # Create tasks for all personas
        tasks = []
        for persona in personas:
            task = self._execute_single_persona(query, persona, context)
            tasks.append(task)

        # Execute all in parallel with timeout
        try:
            responses = await asyncio.gather(*tasks, return_exceptions=True)

            # Convert exceptions to error responses
            processed_responses = []
            for i, response in enumerate(responses):
                if isinstance(response, Exception):
                    processed_responses.append(
                        PersonaResponse(
                            persona_name=personas[i],
                            response="",
                            confidence=0.0,
                            execution_time_ms=0,
                            success=False,
                            error=str(response)
                        )
                    )
                else:
                    processed_responses.append(response)

            return processed_responses

        except Exception as e:
            logger.error(f"❌ Parallel execution failed: {e}")
            # Return error responses for all personas
            return [
                PersonaResponse(
                    persona_name=persona,
                    response="",
                    confidence=0.0,
                    execution_time_ms=0,
                    success=False,
                    error=str(e)
                )
                for persona in personas
            ]

    async def _execute_sequential(
        self,
        query: str,
        personas: List[str],
        context: Optional[Dict]
    ) -> List[PersonaResponse]:
        """Execute personas sequentially (one after another)"""
        logger.info(f"   → Executing {len(personas)} personas SEQUENTIALLY")

        responses = []
        accumulated_context = context.copy() if context else {}

        for i, persona in enumerate(personas):
            logger.info(f"      [{i+1}/{len(personas)}] Executing: {persona}")

            # Add previous responses to context
            if i > 0:
                accumulated_context["previous_responses"] = [
                    {"persona": r.persona_name, "response": r.response}
                    for r in responses
                ]

            response = await self._execute_single_persona(query, persona, accumulated_context)
            responses.append(response)

            # If persona fails, continue with others
            if not response.success:
                logger.warning(f"      ⚠️  {persona} failed, continuing...")

        return responses

    async def _execute_hybrid(
        self,
        query: str,
        personas: List[str],
        context: Optional[Dict]
    ) -> List[PersonaResponse]:
        """Execute hybrid: leader first, then parallel followers"""
        logger.info(f"   → Executing HYBRID: leader + {len(personas)-1} followers")

        if not personas:
            return []

        responses = []

        # 1. Execute leader persona first
        leader = personas[0]
        logger.info(f"      [LEADER] Executing: {leader}")
        leader_response = await self._execute_single_persona(query, leader, context)
        responses.append(leader_response)

        # 2. Execute followers in parallel with leader's context
        if len(personas) > 1:
            followers = personas[1:]
            logger.info(f"      [FOLLOWERS] Executing {len(followers)} in parallel")

            # Add leader's response to context
            enhanced_context = context.copy() if context else {}
            enhanced_context["leader_response"] = {
                "persona": leader_response.persona_name,
                "response": leader_response.response,
                "confidence": leader_response.confidence
            }

            # Execute followers in parallel
            follower_tasks = [
                self._execute_single_persona(query, persona, enhanced_context)
                for persona in followers
            ]

            follower_responses = await asyncio.gather(*follower_tasks, return_exceptions=True)

            # Process follower responses
            for i, response in enumerate(follower_responses):
                if isinstance(response, Exception):
                    responses.append(
                        PersonaResponse(
                            persona_name=followers[i],
                            response="",
                            confidence=0.0,
                            execution_time_ms=0,
                            success=False,
                            error=str(response)
                        )
                    )
                else:
                    responses.append(response)

        return responses

    async def _execute_single_persona(
        self,
        query: str,
        persona: str,
        context: Optional[Dict]
    ) -> PersonaResponse:
        """
        Execute query with a single persona

        For now, this is a simulation. In production, this would call
        the actual orchestrator with the specific persona.
        """
        start_time = time.time()

        try:
            # Simulate persona execution
            # TODO: Replace with actual orchestrator call
            # result = await self.orchestrator.orchestrate(
            #     task=query,
            #     strategy="persona",
            #     context={"persona_key": persona, **(context or {})}
            # )

            # Simulated response (for Phase 2 development)
            await asyncio.sleep(0.1)  # Simulate processing time

            response_text = f"Response from {persona} for query: {query[:50]}..."
            confidence = 0.75 + (hash(persona) % 25) / 100  # Simulated confidence

            execution_time_ms = int((time.time() - start_time) * 1000)

            return PersonaResponse(
                persona_name=persona,
                response=response_text,
                confidence=confidence,
                execution_time_ms=execution_time_ms,
                success=True,
                metadata={
                    "simulated": True,
                    "context_size": len(str(context)) if context else 0
                }
            )

        except Exception as e:
            logger.error(f"❌ Persona {persona} failed: {e}")
            execution_time_ms = int((time.time() - start_time) * 1000)

            return PersonaResponse(
                persona_name=persona,
                response="",
                confidence=0.0,
                execution_time_ms=execution_time_ms,
                success=False,
                error=str(e)
            )

    def _update_stats(self, result: SwarmResult):
        """Update execution statistics"""
        self.execution_stats["total_swarms"] += 1
        self.execution_stats["total_personas_executed"] += len(result.personas)

        # Update average time
        current_avg = self.execution_stats["average_time_ms"]
        total = self.execution_stats["total_swarms"]
        new_avg = ((current_avg * (total - 1)) + result.total_time_ms) / total
        self.execution_stats["average_time_ms"] = int(new_avg)

        # Update success rate
        total_executions = self.execution_stats["total_personas_executed"]
        successful = sum(
            r.success
            for swarm_result in [result]  # In real implementation, track all results
            for r in swarm_result.individual_responses
        )
        self.execution_stats["success_rate"] = successful / total_executions if total_executions > 0 else 0.0

    def get_stats(self) -> Dict[str, Any]:
        """Get execution statistics"""
        return self.execution_stats.copy()


# Convenience function
async def execute_swarm(
    query: str,
    personas: List[str],
    mode: ExecutionMode = ExecutionMode.PARALLEL,
    context: Optional[Dict[str, Any]] = None,
    orchestrator=None
) -> SwarmResult:
    """Execute swarm (convenience async function)"""
    executor = SwarmExecutor(orchestrator)
    return await executor.execute_swarm(query, personas, mode, context)


if __name__ == "__main__":
    # Test the Swarm Executor
    async def test_swarm():
        print("=" * 80)
        print("SWARM EXECUTOR TEST")
        print("=" * 80)

        executor = SwarmExecutor()

        # Test 1: Parallel execution
        print("\n1. Testing PARALLEL execution with 3 personas:")
        result1 = await executor.execute_swarm(
            query="Design a scalable microservices architecture",
            personas=["system-architect", "backend-developer", "devops-engineer"],
            mode=ExecutionMode.PARALLEL
        )

        print(f"   Total time: {result1.total_time_ms}ms")
        print(f"   Success: {result1.success_count}/{len(result1.personas)}")
        for response in result1.individual_responses:
            print(f"   - {response.persona_name}: {response.execution_time_ms}ms")

        # Test 2: Sequential execution
        print("\n2. Testing SEQUENTIAL execution with 3 personas:")
        result2 = await executor.execute_swarm(
            query="Review and improve this code",
            personas=["senior-developer", "code-reviewer", "performance-expert"],
            mode=ExecutionMode.SEQUENTIAL
        )

        print(f"   Total time: {result2.total_time_ms}ms")
        print(f"   Success: {result2.success_count}/{len(result2.personas)}")

        # Test 3: Hybrid execution
        print("\n3. Testing HYBRID execution (leader + followers):")
        result3 = await executor.execute_swarm(
            query="Security audit of authentication system",
            personas=["security-expert", "penetration-tester", "compliance-specialist"],
            mode=ExecutionMode.HYBRID
        )

        print(f"   Total time: {result3.total_time_ms}ms")
        print(f"   Leader: {result3.individual_responses[0].persona_name}")
        print(f"   Followers: {', '.join(r.persona_name for r in result3.individual_responses[1:])}")

        # Statistics
        print("\n4. Execution Statistics:")
        stats = executor.get_stats()
        print(f"   Total swarms: {stats['total_swarms']}")
        print(f"   Total personas executed: {stats['total_personas_executed']}")
        print(f"   Average time: {stats['average_time_ms']}ms")
        print(f"   Success rate: {stats['success_rate']*100:.1f}%")

    # Run test
    asyncio.run(test_swarm())

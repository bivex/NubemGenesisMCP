"""
End-to-End Tests with Real LLMs
Tests complete workflows with actual LLM calls (Anthropic Claude)
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.llm_integration import get_llm, LLMConfig, LLMProvider
from core.multi_persona_collaboration import MultiPersonaCollaboration, CollaborationMode
from core.rag_enhanced_response import get_rag_system
from core.personas_extended import get_persona
from core.persona_memory import get_persona_memory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class E2ETestRunner:
    """End-to-End Test Runner"""

    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0

    def log_result(self, test_name: str, passed: bool, message: str = ""):
        """Log test result"""
        status = "✓ PASS" if passed else "✗ FAIL"
        self.results.append((test_name, passed, message))

        if passed:
            self.passed += 1
            logger.info(f"{status}: {test_name}")
        else:
            self.failed += 1
            logger.error(f"{status}: {test_name} - {message}")

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*60)
        print("E2E TEST SUMMARY")
        print("="*60)

        for test_name, passed, message in self.results:
            status = "✓" if passed else "✗"
            print(f"{status} {test_name}")
            if message and not passed:
                print(f"    {message}")

        print("\n" + "-"*60)
        print(f"Total: {len(self.results)} tests")
        print(f"Passed: {self.passed}")
        print(f"Failed: {self.failed}")
        print(f"Success Rate: {(self.passed/len(self.results)*100):.1f}%")
        print("="*60)


async def test_llm_basic():
    """Test 1: Basic LLM Call"""
    runner = E2ETestRunner()

    print("\n" + "="*60)
    print("TEST 1: Basic LLM Integration")
    print("="*60)

    # Check API key
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        runner.log_result("API Key Check", False, "ANTHROPIC_API_KEY not set")
        runner.print_summary()
        return runner

    runner.log_result("API Key Check", True)

    try:
        # Initialize LLM
        llm = get_llm()
        runner.log_result("LLM Initialization", True)

        # Simple query
        response = await llm.generate(
            prompt="Say 'Hello from Claude' in exactly 3 words.",
            system_prompt="You are a helpful assistant. Be concise."
        )

        has_content = len(response.content) > 0
        runner.log_result("LLM Response Generation", has_content)

        if has_content:
            print(f"\n  Response: {response.content[:100]}")
            print(f"  Model: {response.model}")
            print(f"  Tokens: {response.tokens_used}")

    except Exception as e:
        runner.log_result("LLM Response Generation", False, str(e))

    runner.print_summary()
    return runner


async def test_persona_integration():
    """Test 2: Persona-based LLM Calls"""
    runner = E2ETestRunner()

    print("\n" + "="*60)
    print("TEST 2: Persona Integration")
    print("="*60)

    # Check API key
    if not os.getenv('ANTHROPIC_API_KEY'):
        runner.log_result("API Key Check", False, "ANTHROPIC_API_KEY not set")
        runner.print_summary()
        return runner

    try:
        # Test with product manager persona
        persona = get_persona('product-manager')
        runner.log_result("Persona Loading", persona is not None)

        if persona:
            llm = get_llm()

            response = await llm.generate(
                prompt="List 3 key metrics for a SaaS product in one sentence.",
                system_prompt=persona['system_prompt'][:500]  # Truncate for test
            )

            has_content = len(response.content) > 0
            runner.log_result("Persona-based Generation", has_content)

            if has_content:
                print(f"\n  Response (Product Manager): {response.content[:150]}...")
                print(f"  Tokens: {response.tokens_used}")

    except Exception as e:
        runner.log_result("Persona-based Generation", False, str(e))

    runner.print_summary()
    return runner


async def test_collaboration_sequential():
    """Test 3: Sequential Collaboration"""
    runner = E2ETestRunner()

    print("\n" + "="*60)
    print("TEST 3: Sequential Collaboration")
    print("="*60)

    if not os.getenv('ANTHROPIC_API_KEY'):
        runner.log_result("API Key Check", False, "ANTHROPIC_API_KEY not set")
        runner.print_summary()
        return runner

    try:
        # Initialize collaboration
        collab = MultiPersonaCollaboration(mode=CollaborationMode.SEQUENTIAL)
        runner.log_result("Collaboration Initialization", True)

        # Simple task
        task = "Suggest 3 programming best practices in one sentence each"

        result = await collab.collaborate(
            task=task,
            persona_keys=['senior-developer', 'code-reviewer'],
            num_personas=2
        )

        has_synthesis = len(result.synthesis) > 0
        has_contributions = len(result.contributions) >= 2

        runner.log_result("Sequential Collaboration", has_synthesis and has_contributions)

        if has_synthesis:
            print(f"\n  Contributions: {len(result.contributions)}")
            print(f"  Consensus Score: {result.consensus_score:.2f}")
            print(f"  Time: {result.execution_time:.2f}s")
            print(f"\n  Synthesis Preview: {result.synthesis[:200]}...")

    except Exception as e:
        runner.log_result("Sequential Collaboration", False, str(e))

    runner.print_summary()
    return runner


async def test_collaboration_parallel():
    """Test 4: Parallel Collaboration"""
    runner = E2ETestRunner()

    print("\n" + "="*60)
    print("TEST 4: Parallel Collaboration")
    print("="*60)

    if not os.getenv('ANTHROPIC_API_KEY'):
        runner.log_result("API Key Check", False, "ANTHROPIC_API_KEY not set")
        runner.print_summary()
        return runner

    try:
        collab = MultiPersonaCollaboration(mode=CollaborationMode.PARALLEL)
        runner.log_result("Parallel Mode Initialization", True)

        task = "Name one key consideration for API design"

        result = await collab.collaborate(
            task=task,
            persona_keys=['senior-developer', 'system-architect'],
            num_personas=2
        )

        success = len(result.contributions) >= 2
        runner.log_result("Parallel Collaboration", success)

        if success:
            print(f"\n  Personas: {[c.persona_key for c in result.contributions]}")
            print(f"  Time: {result.execution_time:.2f}s")

    except Exception as e:
        runner.log_result("Parallel Collaboration", False, str(e))

    runner.print_summary()
    return runner


async def test_rag_simple():
    """Test 5: Simple RAG (without vector DB)"""
    runner = E2ETestRunner()

    print("\n" + "="*60)
    print("TEST 5: RAG System (No Vector DB)")
    print("="*60)

    if not os.getenv('ANTHROPIC_API_KEY'):
        runner.log_result("API Key Check", False, "ANTHROPIC_API_KEY not set")
        runner.print_summary()
        return runner

    try:
        # Initialize RAG system
        rag = get_rag_system('senior-developer')
        runner.log_result("RAG System Initialization", True)

        # Check status
        status = rag.get_system_status()
        print(f"\n  RAG Status:")
        print(f"    - Persona: {status['persona_key']}")
        print(f"    - Vector DB: {status['vector_db_available']}")
        print(f"    - Memory: {status['memory_available']}")

        # Generate response (will work even without vector DB)
        result = await rag.generate_response(
            query="What is a design pattern?",
            max_tokens=100
        )

        has_response = len(result.response) > 0
        runner.log_result("RAG Response Generation", has_response)

        if has_response:
            print(f"\n  Response Preview: {result.response[:150]}...")
            print(f"  Execution Time: {result.execution_time:.2f}s")
            print(f"  Tokens Used: {result.tokens_used}")

    except Exception as e:
        runner.log_result("RAG Response Generation", False, str(e))

    runner.print_summary()
    return runner


async def test_memory_system():
    """Test 6: Memory System (without Vector DB)"""
    runner = E2ETestRunner()

    print("\n" + "="*60)
    print("TEST 6: Memory System")
    print("="*60)

    try:
        # Get memory for a persona
        memory = get_persona_memory('senior-developer')
        runner.log_result("Memory System Initialization", True)

        stats = memory.get_memory_stats()
        print(f"\n  Memory Stats:")
        print(f"    - Enabled: {stats['enabled']}")
        print(f"    - Cache Size: {stats['cache_size']}")
        print(f"    - Vector DB: {stats['vector_db_available']}")

        # Try to add memory (will work with cache even without vector DB)
        success = memory.add_memory(
            content="Always write unit tests for critical functions",
            memory_type='learning',
            importance=0.9
        )

        runner.log_result("Memory Add Operation", success or not stats['enabled'])

        if success:
            print(f"  ✓ Memory added successfully")
        elif not stats['enabled']:
            print(f"  ℹ Memory system disabled (expected without Vector DB)")

    except Exception as e:
        runner.log_result("Memory System", False, str(e))

    runner.print_summary()
    return runner


async def run_all_tests():
    """Run all E2E tests"""
    print("\n" + "="*70)
    print(" "*20 + "E2E TESTS WITH REAL LLMS")
    print("="*70)

    # Check prerequisites
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        print("\n⚠️  WARNING: ANTHROPIC_API_KEY not set")
        print("  Set it to run tests with real LLM calls:")
        print("  export ANTHROPIC_API_KEY=your_key")
        print("\nSkipping LLM tests...")
        return

    print(f"\n✓ ANTHROPIC_API_KEY found")
    print("  Running tests with real Claude API calls...")

    # Run tests
    results = []

    results.append(await test_llm_basic())
    results.append(await test_persona_integration())
    results.append(await test_collaboration_sequential())
    results.append(await test_collaboration_parallel())
    results.append(await test_rag_simple())
    results.append(await test_memory_system())

    # Overall summary
    total_passed = sum(r.passed for r in results)
    total_failed = sum(r.failed for r in results)
    total_tests = total_passed + total_failed

    print("\n" + "="*70)
    print(" "*20 + "OVERALL E2E TEST RESULTS")
    print("="*70)
    print(f"\nTotal Tests: {total_tests}")
    print(f"Passed: {total_passed} ✓")
    print(f"Failed: {total_failed} ✗")
    print(f"Success Rate: {(total_passed/total_tests*100) if total_tests > 0 else 0:.1f}%")

    if total_failed == 0:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print(f"\n⚠️  {total_failed} test(s) failed")

    print("="*70)


if __name__ == "__main__":
    # Run tests
    asyncio.run(run_all_tests())

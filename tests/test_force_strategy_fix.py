#!/usr/bin/env python3
"""
Test Bug #3 Fix: force_strategy Parameter
Verifica que el parámetro force_strategy se respete en las consultas
"""

import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.trinity_router import TrinityRouter, StrategyType
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


async def test_force_strategy():
    """Test that force_strategy parameter is respected"""

    print("\n" + "="*80)
    print("🧪 TESTING BUG #3 FIX: force_strategy PARAMETER")
    print("="*80 + "\n")

    router = TrinityRouter()

    # Test cases with different forced strategies
    test_cases = [
        {
            "name": "Force SINGLE strategy",
            "query": "What is the weather today?",
            "force_strategy": StrategyType.SINGLE,
            "expected": StrategyType.SINGLE
        },
        {
            "name": "Force SWARM strategy",
            "query": "Design a complex microservices architecture",
            "force_strategy": StrategyType.SWARM,
            "expected": StrategyType.SWARM
        },
        {
            "name": "Force RAG_ENHANCED strategy",
            "query": "Explain the NubemSuperFClaude persona system",
            "force_strategy": StrategyType.RAG_ENHANCED,
            "expected": StrategyType.RAG_ENHANCED
        },
        {
            "name": "Force HYBRID strategy",
            "query": "Create a comprehensive DevOps pipeline with documentation",
            "force_strategy": StrategyType.HYBRID,
            "expected": StrategyType.HYBRID
        },
        {
            "name": "No force_strategy (auto-selection)",
            "query": "What is 2+2?",
            "force_strategy": None,
            "expected": None  # Should auto-select (probably SINGLE)
        }
    ]

    passed = 0
    failed = 0
    total = len(test_cases)

    for i, test_case in enumerate(test_cases, 1):
        try:
            print(f"\n📝 Test {i}/{total}: {test_case['name']}")
            print(f"   Query: {test_case['query'][:60]}...")

            if test_case['force_strategy']:
                print(f"   Force Strategy: {test_case['force_strategy'].value}")

            # Call router with optional force_strategy
            result = await router.route(
                query=test_case['query'],
                context={},
                force_strategy=test_case['force_strategy']
            )

            print(f"   Selected Strategy: {result.strategy.value}")

            # Verify result
            if test_case['expected'] is None:
                # Auto-selection test - just verify it selected something valid
                if result.strategy in [StrategyType.SINGLE, StrategyType.SWARM,
                                      StrategyType.RAG_ENHANCED, StrategyType.HYBRID]:
                    print(f"   ✅ PASS - Auto-selected valid strategy: {result.strategy.value}")
                    passed += 1
                else:
                    print(f"   ❌ FAIL - Invalid strategy selected: {result.strategy.value}")
                    failed += 1
            else:
                # Force strategy test - verify exact match
                if result.strategy == test_case['expected']:
                    print(f"   ✅ PASS - Forced strategy respected!")
                    passed += 1
                else:
                    print(f"   ❌ FAIL - Expected {test_case['expected'].value}, got {result.strategy.value}")
                    failed += 1

        except Exception as e:
            print(f"   ❌ FAIL - Exception: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    # Test invalid strategy handling through context string
    print(f"\n📝 Test {total + 1}/{total + 1}: Invalid force_strategy handling")
    print(f"   Testing with invalid strategy string in context")

    try:
        # Simulate what mcp_server does with context
        context = {"force_strategy": "invalid_strategy"}
        force_strategy_str = context.get("force_strategy")
        force_strategy = None

        try:
            force_strategy = StrategyType(force_strategy_str)
        except ValueError:
            logger.info(f"❌ Invalid force_strategy: {force_strategy_str}, ignoring")
            force_strategy = None

        result = await router.route(
            query="Test query",
            context=context,
            force_strategy=force_strategy
        )

        if force_strategy is None and result.strategy in [StrategyType.SINGLE, StrategyType.SWARM,
                                                          StrategyType.RAG_ENHANCED, StrategyType.HYBRID]:
            print(f"   ✅ PASS - Invalid strategy ignored, auto-selected: {result.strategy.value}")
            passed += 1
        else:
            print(f"   ❌ FAIL - Invalid strategy not handled correctly")
            failed += 1

    except Exception as e:
        print(f"   ❌ FAIL - Exception: {e}")
        failed += 1

    # Summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)
    print(f"Total tests:  {total + 1}")
    print(f"Passed:       {passed} ✅")
    print(f"Failed:       {failed} ❌")
    print(f"Success rate: {passed/(total+1)*100:.1f}%")
    print("="*80 + "\n")

    if failed == 0:
        print("🎉 ALL TESTS PASSED! Bug #3 fix is working correctly!\n")
        return True
    else:
        print(f"❌ {failed} tests failed. Bug #3 fix needs more work.\n")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_force_strategy())
    sys.exit(0 if success else 1)

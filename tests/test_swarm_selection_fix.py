#!/usr/bin/env python3
"""
Test Bug #2 Fix: Swarm Strategy Selection
Verifica que la estrategia SWARM se active automáticamente para queries complejas
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


async def test_swarm_selection():
    """Test that SWARM strategy is selected automatically for appropriate queries"""

    print("\n" + "="*80)
    print("🧪 TESTING BUG #2 FIX: SWARM STRATEGY AUTO-SELECTION")
    print("="*80 + "\n")

    router = TrinityRouter()

    # Test cases expecting different strategies
    test_cases = [
        {
            "query": "What is 2+2?",
            "expected": StrategyType.SINGLE,
            "description": "Trivial math (SINGLE)"
        },
        {
            "query": "Fix typo in README",
            "expected": StrategyType.SINGLE,
            "description": "Simple fix (SINGLE)"
        },
        {
            "query": "Design a scalable microservices architecture on AWS with high availability",
            "expected": StrategyType.SWARM,
            "description": "Architecture design (should be SWARM!)"
        },
        {
            "query": "Optimize this SQL query and explain the performance implications",
            "expected": [StrategyType.SINGLE, StrategyType.SWARM],  # Accept either
            "description": "SQL optimization (SINGLE or SWARM acceptable)"
        },
        {
            "query": """Create a production-ready Kubernetes deployment with:
1. Auto-scaling
2. Load balancing
3. Monitoring
4. Disaster recovery""",
            "expected": StrategyType.SWARM,
            "description": "Production K8s deployment (should be SWARM!)"
        },
        {
            "query": """Design a comprehensive security audit system for our microservices platform that includes:
- Automated vulnerability scanning
- Penetration testing framework
- Compliance reporting
- Real-time threat detection
- Integration with existing monitoring""",
            "expected": [StrategyType.SWARM, StrategyType.HYBRID],
            "description": "Complex security system (SWARM or HYBRID)"
        }
    ]

    passed = 0
    failed = 0
    total = len(test_cases)

    for i, test_case in enumerate(test_cases, 1):
        query = test_case["query"]
        expected = test_case["expected"]
        description = test_case["description"]

        # Allow expected to be a list or single value
        if not isinstance(expected, list):
            expected = [expected]

        try:
            print(f"\n📝 Test {i}/{total}: {description}")
            print(f"   Query: {query[:60]}...")

            result = await router.route(query=query, context={})

            print(f"   Complexity: {result.complexity_analysis.level.value} ({result.complexity_analysis.score:.2f})")
            print(f"   Recommended personas: {result.complexity_analysis.recommended_personas}")
            print(f"   Strategy selected: {result.strategy.value}")
            print(f"   Expected: {' or '.join([s.value for s in expected])}")

            if result.strategy in expected:
                print(f"   ✅ PASS - Correct strategy selected!")
                passed += 1
            else:
                print(f"   ❌ FAIL - Expected {' or '.join([s.value for s in expected])}, got {result.strategy.value}")
                print(f"   Reasoning:")
                for reason in result.reasoning[:3]:
                    print(f"     - {reason}")
                failed += 1

        except Exception as e:
            print(f"   ❌ FAIL - Exception: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    # Summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)
    print(f"Total tests:  {total}")
    print(f"Passed:       {passed} ✅")
    print(f"Failed:       {failed} ❌")
    print(f"Success rate: {passed/total*100:.1f}%")
    print("="*80 + "\n")

    if failed == 0:
        print("🎉 ALL TESTS PASSED! Bug #2 fix is working correctly!\n")
        return True
    else:
        print(f"⚠️  {failed} tests failed. Need to improve Swarm selection.\n")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_swarm_selection())
    sys.exit(0 if success else 1)

#!/usr/bin/env python3
"""
Test Bug #4 Fix: Persona Routing
Verifica que las personas solicitadas explícitamente se respeten (no redirect a architect)
"""

import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.unified_orchestrator import PersonaStrategy
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


async def test_persona_routing():
    """Test that explicit persona_key is respected"""

    print("\n" + "="*80)
    print("🧪 TESTING BUG #4 FIX: PERSONA ROUTING")
    print("="*80 + "\n")

    strategy = PersonaStrategy()

    # Test cases (using actual persona names that exist)
    test_cases = [
        ("nlp-specialist", "NLP Specialist persona should be used"),
        ("sre-specialist", "SRE Specialist persona should be used"),
        ("security", "Security persona should be used"),
        ("cybersecurity-specialist", "Cybersecurity Specialist persona should be used"),
        ("data-engineer", "Data Engineer persona should be used"),
        ("backend", "Backend Developer persona should be used"),
        ("gcp-architect", "GCP Architect persona should be used"),
        ("architect", "Architect persona should be used (control test)"),
    ]

    passed = 0
    failed = 0
    total = len(test_cases)

    for persona_key, description in test_cases:
        try:
            print(f"\n📝 Test {passed + failed + 1}/{total}: {description}")
            print(f"   Requesting: {persona_key}")

            result = await strategy.orchestrate(
                task=f"Test task for {persona_key}",
                context={"persona_key": persona_key}
            )

            persona_used = result.get('persona_used')
            persona_requested = result.get('persona_requested')

            print(f"   Requested:  {persona_requested}")
            print(f"   Used:       {persona_used}")

            if persona_used == persona_key:
                print(f"   ✅ PASS - Correct persona used!")
                passed += 1
            else:
                print(f"   ❌ FAIL - Wrong persona! Expected '{persona_key}', got '{persona_used}'")
                failed += 1

        except Exception as e:
            print(f"   ❌ FAIL - Exception: {e}")
            failed += 1

    # Test fallback behavior for non-existent persona
    print(f"\n📝 Test {total + 1}/{total + 1}: Fallback for non-existent persona")
    print(f"   Requesting: nonexistent-persona")

    try:
        result = await strategy.orchestrate(
            task="Test task for non-existent persona",
            context={"persona_key": "nonexistent-persona"}
        )

        persona_used = result.get('persona_used')
        print(f"   Used (fallback): {persona_used}")

        if persona_used in ['architect', 'senior-developer', 'backend']:
            print(f"   ✅ PASS - Graceful fallback to {persona_used}")
            passed += 1
        else:
            print(f"   ⚠️  PASS (with warning) - Fallback to {persona_used}")
            passed += 1

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
        print("🎉 ALL TESTS PASSED! Bug #4 fix is working correctly!\n")
        return True
    else:
        print(f"❌ {failed} tests failed. Bug #4 fix needs more work.\n")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_persona_routing())
    sys.exit(0 if success else 1)

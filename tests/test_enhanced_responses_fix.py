#!/usr/bin/env python3
"""
Test Bug #5 Fix: Enhanced Persona Responses
Verifica que las personas generen respuestas específicas y útiles
"""

import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.personas_unified import Persona
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


async def test_enhanced_responses():
    """Test that personas generate specific, useful responses"""

    print("\n" + "="*80)
    print("🧪 TESTING BUG #5 FIX: ENHANCED PERSONA RESPONSES")
    print("="*80 + "\n")

    # Create a test persona
    test_persona = Persona(
        name="architect",
        identity="System Architect",
        specialties=["microservices", "cloud architecture", "scalability"],
        system_prompt="You are a senior system architect",
        capabilities=["design", "architecture", "review"],
        commands=[],
        confidence_scores={"design": 0.9, "architecture": 0.95},
        level="L4"
    )

    # Test cases for different task types
    test_cases = [
        {
            "task": "Design a scalable microservices architecture",
            "expected_type": "design",
            "context": {"domain": "backend", "complexity": "complex", "strategy": "swarm"},
            "description": "Design task"
        },
        {
            "task": "Implement a user authentication system",
            "expected_type": "implement",
            "context": {"domain": "security", "complexity": "moderate"},
            "description": "Implementation task"
        },
        {
            "task": "Optimize the database query performance",
            "expected_type": "optimize",
            "context": {"domain": "data", "complexity": "moderate"},
            "description": "Optimization task"
        },
        {
            "task": "Debug the login error",
            "expected_type": "debug",
            "context": {"domain": "general", "complexity": "simple"},
            "description": "Debug task"
        },
        {
            "task": "Explain how microservices work",
            "expected_type": "explain",
            "context": {"domain": "architecture", "complexity": "simple"},
            "description": "Explanation task"
        }
    ]

    passed = 0
    failed = 0
    total = len(test_cases)

    for i, test_case in enumerate(test_cases, 1):
        task = test_case["task"]
        expected_type = test_case["expected_type"]
        context = test_case["context"]
        description = test_case["description"]

        print(f"\n📝 Test {i}/{total}: {description}")
        print(f"   Task: {task}")

        # Execute the persona
        result = await test_persona.execute(task, context)

        print(f"   Task type detected: {result.get('task_type')}")
        print(f"   Confidence: {result.get('confidence', 0):.2f}")

        # Verify task type detection
        if result.get('task_type') != expected_type:
            print(f"   ⚠️  WARNING: Expected task_type '{expected_type}', got '{result.get('task_type')}'")

        # Verify result is not generic stub
        result_text = result.get('result', '')

        # Check for enhanced response indicators
        is_enhanced = any([
            "**Task:**" in result_text,
            "**Approach:**" in result_text,
            "**Strategy:**" in result_text,
            len(result_text) > 200,  # Enhanced responses are longer
            "System Architect" in result_text,  # Uses identity
            test_persona.specialties[0] in result_text,  # Uses specialties
        ])

        # Verify metadata includes Trinity analysis
        metadata = result.get('metadata', {})
        trinity_analysis = metadata.get('trinity_analysis', {})
        has_trinity = all([
            'domain' in trinity_analysis,
            'complexity' in trinity_analysis,
            'strategy' in trinity_analysis
        ])

        if is_enhanced and has_trinity:
            print(f"   ✅ PASS - Enhanced response with Trinity context!")
            print(f"   Response length: {len(result_text)} chars")
            print(f"   Trinity context: {trinity_analysis}")
            passed += 1
        else:
            print(f"   ❌ FAIL - Response is still generic!")
            if not is_enhanced:
                print(f"      - Response not enhanced (length: {len(result_text)})")
            if not has_trinity:
                print(f"      - Missing Trinity context")
            print(f"   Result preview: {result_text[:150]}...")
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

    # Show example output
    if passed > 0:
        print("📄 EXAMPLE ENHANCED RESPONSE:")
        print("="*80)
        example_result = await test_persona.execute(
            "Design a scalable microservices architecture",
            {"domain": "backend", "complexity": "complex", "strategy": "swarm"}
        )
        print(example_result['result'][:500] + "...")
        print("="*80 + "\n")

    if failed == 0:
        print("🎉 ALL TESTS PASSED! Bug #5 fix is working correctly!\n")
        return True
    else:
        print(f"⚠️  {failed} tests failed. Need improvements.\n")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_enhanced_responses())
    sys.exit(0 if success else 1)

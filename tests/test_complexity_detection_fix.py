#!/usr/bin/env python3
"""
Test Bug #1 Fix: Complexity Detection
Verifica que las queries complejas se detecten correctamente
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.complexity_evaluator import ComplexityEvaluator, ComplexityLevel


def test_complexity_detection():
    """Test that complex queries are detected correctly"""

    print("\n" + "="*80)
    print("🧪 TESTING BUG #1 FIX: COMPLEXITY DETECTION")
    print("="*80 + "\n")

    evaluator = ComplexityEvaluator()

    # Test cases with expected minimum levels
    test_cases = [
        {
            "query": "Fix typo in README",
            "expected_min": ComplexityLevel.TRIVIAL,
            "expected_max": ComplexityLevel.SIMPLE,
            "description": "Simple typo fix"
        },
        {
            "query": "Review my Python code for bugs",
            "expected_min": ComplexityLevel.TRIVIAL,
            "expected_max": ComplexityLevel.SIMPLE,
            "description": "Code review"
        },
        {
            "query": "Optimize this SQL query and explain the performance implications",
            "expected_min": ComplexityLevel.SIMPLE,
            "expected_max": ComplexityLevel.MODERATE,
            "description": "SQL optimization with explanation"
        },
        {
            "query": "Design a scalable microservices architecture on AWS with high availability",
            "expected_min": ComplexityLevel.MODERATE,
            "expected_max": ComplexityLevel.COMPLEX,
            "description": "Architecture design (should be MODERATE or COMPLEX!)"
        },
        {
            "query": """Create a production-ready Kubernetes deployment with:
1. Auto-scaling
2. Load balancing
3. Monitoring
4. Disaster recovery""",
            "expected_min": ComplexityLevel.MODERATE,
            "expected_max": ComplexityLevel.COMPLEX,
            "description": "Production K8s deployment"
        },
        {
            "query": """Design a comprehensive security audit system for our microservices platform that includes:
- Automated vulnerability scanning
- Penetration testing framework
- Compliance reporting
- Real-time threat detection
- Integration with existing monitoring""",
            "expected_min": ComplexityLevel.COMPLEX,
            "expected_max": ComplexityLevel.EXPERT,
            "description": "Complex security system (should be COMPLEX or EXPERT!)"
        }
    ]

    passed = 0
    failed = 0
    total = len(test_cases)

    for i, test_case in enumerate(test_cases, 1):
        query = test_case["query"]
        expected_min = test_case["expected_min"]
        expected_max = test_case["expected_max"]
        description = test_case["description"]

        result = evaluator.evaluate(query)

        print(f"\n📝 Test {i}/{total}: {description}")
        print(f"   Query: {query[:60]}...")
        print(f"   Complexity: {result.level.value} ({result.score:.2f})")
        print(f"   Expected: {expected_min.value} to {expected_max.value}")
        print(f"   Personas: {result.recommended_personas}")
        print(f"   Time: {result.estimated_time_seconds}s")

        # Show top factors
        sorted_factors = sorted(result.factors.items(), key=lambda x: x[1], reverse=True)
        print(f"   Top factors:")
        for factor_name, factor_score in sorted_factors[:3]:
            if factor_score > 0:
                print(f"     - {factor_name}: {factor_score:.2f}")

        # Level comparison (treating as ordered enum)
        level_order = {
            ComplexityLevel.TRIVIAL: 1,
            ComplexityLevel.SIMPLE: 2,
            ComplexityLevel.MODERATE: 3,
            ComplexityLevel.COMPLEX: 4,
            ComplexityLevel.EXPERT: 5
        }

        actual_order = level_order[result.level]
        min_order = level_order[expected_min]
        max_order = level_order[expected_max]

        if min_order <= actual_order <= max_order:
            print(f"   ✅ PASS - Complexity level within expected range!")
            passed += 1
        else:
            if actual_order < min_order:
                print(f"   ❌ FAIL - Complexity TOO LOW! Got {result.level.value}, expected at least {expected_min.value}")
            else:
                print(f"   ❌ FAIL - Complexity TOO HIGH! Got {result.level.value}, expected at most {expected_max.value}")
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
        print("🎉 ALL TESTS PASSED! Bug #1 fix is working correctly!\n")
        return True
    else:
        print(f"⚠️  {failed} tests failed. Need more tuning.\n")
        return False


if __name__ == "__main__":
    success = test_complexity_detection()
    sys.exit(0 if success else 1)

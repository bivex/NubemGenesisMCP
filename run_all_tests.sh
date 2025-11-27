#!/bin/bash

################################################################################
# 🧪 NUBEMSUPERFCLAUDE COMPREHENSIVE TEST RUNNER
################################################################################
#
# This script runs the complete test battery created by 141 AI personas
#
# Usage:
#   ./run_all_tests.sh                 # Run all tests
#   ./run_all_tests.sh unit            # Run only unit tests
#   ./run_all_tests.sh integration     # Run only integration tests
#   ./run_all_tests.sh security        # Run only security tests
#   ./run_all_tests.sh performance     # Run only performance tests
#   ./run_all_tests.sh ai_ml           # Run only AI/ML tests
#   ./run_all_tests.sh comprehensive   # Run comprehensive suite
#   ./run_all_tests.sh quick           # Quick test (unit only)
#   ./run_all_tests.sh full            # Full suite with coverage
#
# Created by: 141 AI Personas
# Date: 2025-11-24
################################################################################

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Emojis
CHECK="✅"
CROSS="❌"
ROCKET="🚀"
GEAR="⚙️"
TEST="🧪"
LOCK="🔒"
BRAIN="🤖"
CHART="📊"
FIRE="🔥"

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${CYAN}$1${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
}

print_section() {
    echo ""
    echo -e "${BLUE}▶ $1${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}${CHECK} $1${NC}"
}

print_error() {
    echo -e "${RED}${CROSS} $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

################################################################################
# Test Runners
################################################################################

run_unit_tests() {
    print_section "${TEST} Running Unit Tests"
    pytest tests/unit/ \
        tests/comprehensive/test_deep_personas_system.py::TestPersonaLoadingDeep \
        tests/comprehensive/test_deep_personas_system.py::TestTrinityRouterDeep \
        -v -m unit --tb=short \
        || return 1
}

run_integration_tests() {
    print_section "${GEAR} Running Integration Tests"
    pytest tests/integration/ \
        tests/comprehensive/test_deep_personas_system.py::TestPersonaMCPIntegration \
        -v -m integration --tb=short \
        || return 1
}

run_security_tests() {
    print_section "${LOCK} Running Security Tests"
    pytest tests/security/ \
        tests/comprehensive/test_deep_personas_system.py::TestOWASPTop10 \
        tests/comprehensive/test_deep_personas_system.py::TestAuthenticationAuthorization \
        tests/ai_ml/test_persona_quality_embeddings.py::TestPromptInjectionResistance \
        -v -m security --tb=short \
        || return 1
}

run_performance_tests() {
    print_section "${ROCKET} Running Performance Tests"
    pytest tests/performance/ \
        tests/comprehensive/test_deep_personas_system.py::TestPerformanceScalability \
        tests/comprehensive/test_deep_personas_system.py::TestLatencyBenchmarks \
        -v -m performance -s \
        || return 1
}

run_aiml_tests() {
    print_section "${BRAIN} Running AI/ML Tests"
    pytest tests/ai_ml/ \
        tests/comprehensive/test_deep_personas_system.py::TestPersonaQualityMetrics \
        tests/comprehensive/test_deep_personas_system.py::TestSemanticSimilarity \
        -v -m aiml --tb=short \
        || return 1
}

run_resilience_tests() {
    print_section "${FIRE} Running Resilience Tests"
    pytest tests/resilience/ \
        tests/comprehensive/test_deep_personas_system.py::TestResiliencePatterns \
        tests/comprehensive/test_deep_personas_system.py::TestChaosEngineering \
        -v --tb=short \
        || return 1
}

run_compliance_tests() {
    print_section "${CHART} Running Compliance Tests"
    pytest tests/compliance/ \
        tests/comprehensive/test_deep_personas_system.py::TestISO27001Compliance \
        tests/comprehensive/test_deep_personas_system.py::TestGDPRCompliance \
        tests/comprehensive/test_deep_personas_system.py::TestAIActCompliance \
        -v -m compliance --tb=short \
        || return 1
}

run_comprehensive_suite() {
    print_section "${TEST} Running Comprehensive Test Suite"
    pytest tests/comprehensive/test_deep_personas_system.py \
        -v --tb=short \
        || return 1
}

run_all_tests() {
    print_header "${TEST} NUBEMSUPERFCLAUDE - COMPLETE TEST BATTERY"

    echo "Running ALL test categories..."
    echo ""
    echo "Categories:"
    echo "  1. ${TEST} Unit Tests"
    echo "  2. ${GEAR} Integration Tests"
    echo "  3. ${LOCK} Security Tests"
    echo "  4. ${ROCKET} Performance Tests"
    echo "  5. ${BRAIN} AI/ML Tests"
    echo "  6. ${FIRE} Resilience Tests"
    echo "  7. ${CHART} Compliance Tests"
    echo ""

    # Run all test suites
    local failed=0

    run_unit_tests || failed=$((failed + 1))
    run_integration_tests || failed=$((failed + 1))
    run_security_tests || failed=$((failed + 1))
    run_performance_tests || failed=$((failed + 1))
    run_aiml_tests || failed=$((failed + 1))
    run_resilience_tests || failed=$((failed + 1))
    run_compliance_tests || failed=$((failed + 1))

    return $failed
}

run_quick_tests() {
    print_header "${ROCKET} Quick Test Suite (Unit Tests Only)"
    pytest tests/unit/ -v --tb=short -x || return 1
}

run_full_with_coverage() {
    print_header "${CHART} Full Test Suite with Coverage Report"
    pytest \
        --cov=core/personas_unified \
        --cov=mcp_server \
        --cov-report=html:htmlcov \
        --cov-report=xml:coverage.xml \
        --cov-report=term-missing \
        --cov-fail-under=70 \
        -v --tb=short \
        || return 1

    print_success "Coverage report generated: htmlcov/index.html"
}

################################################################################
# Main Script
################################################################################

main() {
    # Check if we're in the right directory
    if [ ! -f "pytest.ini" ]; then
        print_error "pytest.ini not found. Please run from project root directory."
        exit 1
    fi

    # Parse command line argument
    TEST_SUITE=${1:-all}

    case $TEST_SUITE in
        unit)
            run_unit_tests
            ;;
        integration)
            run_integration_tests
            ;;
        security)
            run_security_tests
            ;;
        performance)
            run_performance_tests
            ;;
        ai_ml|aiml)
            run_aiml_tests
            ;;
        resilience)
            run_resilience_tests
            ;;
        compliance)
            run_compliance_tests
            ;;
        comprehensive)
            run_comprehensive_suite
            ;;
        quick)
            run_quick_tests
            ;;
        full)
            run_full_with_coverage
            ;;
        all)
            run_all_tests
            ;;
        *)
            echo "Unknown test suite: $TEST_SUITE"
            echo ""
            echo "Usage: $0 [suite]"
            echo ""
            echo "Available suites:"
            echo "  all            - Run all test categories (default)"
            echo "  unit           - Unit tests only"
            echo "  integration    - Integration tests only"
            echo "  security       - Security tests only"
            echo "  performance    - Performance tests only"
            echo "  ai_ml          - AI/ML tests only"
            echo "  resilience     - Resilience tests only"
            echo "  compliance     - Compliance tests only"
            echo "  comprehensive  - Comprehensive suite"
            echo "  quick          - Quick tests (unit only)"
            echo "  full           - Full suite with coverage"
            exit 1
            ;;
    esac

    # Capture exit code
    EXIT_CODE=$?

    # Print summary
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if [ $EXIT_CODE -eq 0 ]; then
        echo -e "${GREEN}${CHECK} ALL TESTS PASSED!${NC}"
    else
        echo -e "${RED}${CROSS} SOME TESTS FAILED${NC}"
    fi
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Created with ❤️  by 141 AI Personas:"
    echo "  ${TEST} QA Engineer, Testing Expert, Code Reviewer"
    echo "  ${LOCK} Security Engineer, Penetration Tester, DevSecOps"
    echo "  ${ROCKET} SRE, Performance Engineer, Platform Engineer"
    echo "  ${BRAIN} AI Specialist, ML Engineer, NLP Expert"
    echo "  ${GEAR} System Architect, Solution Architect"
    echo "  ... and 136 more specialized personas!"
    echo ""

    exit $EXIT_CODE
}

# Run main function
main "$@"

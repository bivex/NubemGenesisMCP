#!/usr/bin/env python3
"""
NubemSuperFClaude - Basic Integration Tests
Simple tests that don't require pytest
"""

import os
import sys
from pathlib import Path

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def print_test(name, passed):
    """Print test result with color"""
    if passed:
        print(f"{GREEN}✓{RESET} {name}")
        return 1
    else:
        print(f"{RED}✗{RESET} {name}")
        return 0

def test_structure():
    """Test project structure"""
    print(f"\n{YELLOW}Testing Project Structure...{RESET}")
    passed = 0
    total = 0
    
    base_path = Path(__file__).parent.parent
    
    # Test directories
    expected_dirs = [
        'core',
        'core/personas',
        'security/api-rotation',
        'context/embeddings',
        'context/vector-db',
        'api/rest',
        'tests',
        'docs'
    ]
    
    for dir_path in expected_dirs:
        total += 1
        full_path = base_path / dir_path
        passed += print_test(f"Directory exists: {dir_path}", full_path.exists())
    
    # Test files
    expected_files = [
        'README.md',
        'requirements.txt',
        '.env.example',
        '.gitignore'
    ]
    
    for file_path in expected_files:
        total += 1
        full_path = base_path / file_path
        passed += print_test(f"File exists: {file_path}", full_path.exists())
    
    return passed, total

def test_configuration():
    """Test configuration files"""
    print(f"\n{YELLOW}Testing Configuration...{RESET}")
    passed = 0
    total = 0
    
    base_path = Path(__file__).parent.parent
    
    # Test requirements.txt content
    req_file = base_path / 'requirements.txt'
    if req_file.exists():
        content = req_file.read_text()
        
        deps = [
            ('anthropic', 'Anthropic client'),
            ('fastapi', 'FastAPI framework'),
            ('qdrant-client', 'Qdrant vector DB'),
            ('google-cloud', 'Google Cloud SDK')
        ]
        
        for dep, name in deps:
            total += 1
            passed += print_test(f"Dependency: {name}", dep in content)
    
    # Test .env.example
    env_file = base_path / '.env.example'
    if env_file.exists():
        content = env_file.read_text()
        
        configs = [
            ('CLAUDE_API_KEY', 'Claude API configuration'),
            ('GCP_PROJECT', 'GCP configuration'),
            ('QDRANT_HOST', 'Vector DB configuration'),
            ('NC_MEMORY_SIZE', 'Framework configuration')
        ]
        
        for config, name in configs:
            total += 1
            passed += print_test(f"Config: {name}", config in content)
    
    return passed, total

def test_code_integration():
    """Test code file integration"""
    print(f"\n{YELLOW}Testing Code Integration...{RESET}")
    passed = 0
    total = 0
    
    base_path = Path(__file__).parent.parent
    
    # Check for Python files in core
    core_path = base_path / 'core'
    if core_path.exists():
        py_files = list(core_path.glob('*.py'))
        total += 1
        passed += print_test(f"Python files in core: {len(py_files)} files", len(py_files) > 0)
    
    # Check for personas documentation
    personas_path = base_path / 'core' / 'personas'
    if personas_path.exists():
        md_files = list(personas_path.glob('*.md'))
        total += 1
        passed += print_test(f"Persona docs: {len(md_files)} files", len(md_files) > 0)
    
    # Check for security scripts
    security_path = base_path / 'security' / 'api-rotation'
    if security_path.exists():
        sh_files = list(security_path.glob('*.sh'))
        total += 1
        passed += print_test(f"Security scripts: {len(sh_files)} files", len(sh_files) > 0)
    
    return passed, total

def main():
    """Run all tests"""
    print(f"\n{'='*50}")
    print(f"{YELLOW}NubemSuperFClaude Integration Tests{RESET}")
    print(f"{'='*50}")
    
    total_passed = 0
    total_tests = 0
    
    # Run test suites
    tests = [
        test_structure,
        test_configuration,
        test_code_integration
    ]
    
    for test_func in tests:
        passed, total = test_func()
        total_passed += passed
        total_tests += total
    
    # Print summary
    print(f"\n{'='*50}")
    print(f"{YELLOW}Test Summary{RESET}")
    print(f"{'='*50}")
    
    success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
    
    if success_rate == 100:
        color = GREEN
        status = "ALL TESTS PASSED!"
    elif success_rate >= 70:
        color = YELLOW
        status = "MOSTLY PASSED"
    else:
        color = RED
        status = "NEEDS ATTENTION"
    
    print(f"\nTests passed: {color}{total_passed}/{total_tests}{RESET} ({success_rate:.1f}%)")
    print(f"Status: {color}{status}{RESET}\n")
    
    # Return exit code
    return 0 if success_rate >= 70 else 1

if __name__ == "__main__":
    exit(main())
#!/usr/bin/env python3
"""
Installation Tests for NubemSuperFClaude
Verifies that all dependencies and components are properly installed
"""

import sys
import os
import importlib
import subprocess
from pathlib import Path
from typing import List, Tuple, Dict, Any
import json

# Colors for output
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'  # No Color


def print_colored(message: str, color: str = NC):
    """Print colored message"""
    print(f"{color}{message}{NC}")


def test_python_version() -> Tuple[bool, str]:
    """Test Python version is 3.9+"""
    version = sys.version_info
    if version.major == 3 and version.minor >= 9:
        return True, f"Python {version.major}.{version.minor}.{version.micro}"
    return False, f"Python 3.9+ required, found {version.major}.{version.minor}"


def test_required_modules() -> Tuple[bool, List[str]]:
    """Test all required Python modules are installed"""
    required_modules = [
        # Core
        'fastapi',
        'uvicorn',
        'pydantic',
        'pydantic_settings',
        
        # LLM APIs
        'anthropic',
        'openai',
        
        # Utilities
        'python-dotenv',
        'psutil',
        'jwt',
        'prometheus_client',
        'httpx',
        'aiohttp',
        'aiofiles',
        'rich',
        'click',
        'tqdm',
        
        # Data processing
        'numpy',
        'pandas',
        'sklearn',
        
        # Security
        'cryptography',
        'passlib',
        'jose',
    ]
    
    missing = []
    for module_name in required_modules:
        try:
            # Handle special cases
            if module_name == 'python-dotenv':
                importlib.import_module('dotenv')
            elif module_name == 'sklearn':
                importlib.import_module('sklearn')
            elif module_name == 'jose':
                importlib.import_module('jose')
            else:
                importlib.import_module(module_name)
        except ImportError:
            missing.append(module_name)
    
    if missing:
        return False, missing
    return True, []


def test_core_imports() -> Tuple[bool, List[str]]:
    """Test that core application modules can be imported"""
    core_modules = [
        'core.unified_orchestrator',
        'core.personas_unified',
        'core.multi_llm_verifier',
        'core.secure_secrets_manager',
        'core.api.chat_endpoint',
        'config.validator',
    ]
    
    failed = []
    for module_name in core_modules:
        try:
            importlib.import_module(module_name)
        except Exception as e:
            failed.append(f"{module_name}: {str(e)}")
    
    if failed:
        return False, failed
    return True, []


def test_env_file() -> Tuple[bool, str]:
    """Test that .env file exists and has required keys"""
    env_path = Path('.env')
    
    if not env_path.exists():
        return False, ".env file not found"
    
    # Check for required keys
    required_keys = ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY']
    found_keys = []
    
    with open(env_path, 'r') as f:
        content = f.read()
        for key in required_keys:
            if key in content:
                # Check if it's not a placeholder
                if 'your-' not in content.split(f'{key}=')[1].split('\n')[0]:
                    found_keys.append(key)
    
    if not found_keys:
        return False, "No valid API keys found in .env"
    
    return True, f"Found API keys: {', '.join(found_keys)}"


def test_directories() -> Tuple[bool, List[str]]:
    """Test that required directories exist"""
    required_dirs = ['core', 'api', 'config', 'tests', 'scripts']
    missing = []
    
    for dir_name in required_dirs:
        if not Path(dir_name).is_dir():
            missing.append(dir_name)
    
    if missing:
        return False, missing
    return True, []


def test_api_endpoints() -> Tuple[bool, str]:
    """Test that API server can start and respond"""
    try:
        import requests
        # Try to connect to local server
        response = requests.get('http://localhost:8001/api/health', timeout=2)
        if response.status_code == 200:
            return True, "API server is running"
        return False, f"API returned status {response.status_code}"
    except:
        return False, "API server not running (this is normal for installation test)"


def test_personas_loading() -> Tuple[bool, str]:
    """Test that personas can be loaded"""
    try:
        from core.personas_unified import UnifiedPersonaManager
        manager = UnifiedPersonaManager()
        count = len(manager.personas)
        if count > 0:
            return True, f"Loaded {count} personas"
        return False, "No personas loaded"
    except Exception as e:
        return False, f"Failed to load personas: {str(e)}"


def test_mock_services() -> Tuple[bool, str]:
    """Test that mock services work"""
    try:
        from core.mock_services import MockRedis, MockVectorDB, MockDatabase
        
        # Test MockRedis
        redis = MockRedis()
        
        # Test MockVectorDB  
        vector_db = MockVectorDB()
        
        # Test MockDatabase
        database = MockDatabase()
        
        return True, "Mock services initialized successfully"
    except Exception as e:
        return False, f"Mock services failed: {str(e)}"


def run_all_tests():
    """Run all installation tests"""
    print_colored("\n" + "="*50, BLUE)
    print_colored("🔍 NubemSuperFClaude - Installation Test Suite", BLUE)
    print_colored("="*50 + "\n", BLUE)
    
    tests = [
        ("Python Version", test_python_version),
        ("Required Modules", test_required_modules),
        ("Core Imports", test_core_imports),
        ("Environment File", test_env_file),
        ("Directory Structure", test_directories),
        ("Personas Loading", test_personas_loading),
        ("Mock Services", test_mock_services),
        ("API Endpoints", test_api_endpoints),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"Testing {test_name}... ", end="")
        try:
            success, details = test_func()
            
            if success:
                print_colored("✅ PASSED", GREEN)
                if isinstance(details, str):
                    print_colored(f"  └─ {details}", GREEN)
            else:
                print_colored("❌ FAILED", RED)
                if isinstance(details, list):
                    for item in details:
                        print_colored(f"  └─ Missing: {item}", RED)
                else:
                    print_colored(f"  └─ {details}", RED)
            
            results.append((test_name, success))
            
        except Exception as e:
            print_colored("❌ ERROR", RED)
            print_colored(f"  └─ {str(e)}", RED)
            results.append((test_name, False))
    
    # Summary
    print_colored("\n" + "="*50, BLUE)
    print_colored("📊 TEST SUMMARY", BLUE)
    print_colored("="*50, BLUE)
    
    passed = sum(1 for _, success in results if success)
    failed = len(results) - passed
    
    print(f"\nTotal Tests: {len(results)}")
    print_colored(f"Passed: {passed}", GREEN)
    if failed > 0:
        print_colored(f"Failed: {failed}", RED)
    
    # Overall result
    print_colored("\n" + "="*50, BLUE)
    if failed == 0:
        print_colored("✨ ALL TESTS PASSED! Installation is complete.", GREEN)
        print_colored("You can now start the application with: python main.py", GREEN)
    else:
        print_colored("⚠️ SOME TESTS FAILED", YELLOW)
        print_colored("The application may still work with limited functionality.", YELLOW)
        print_colored("Check the failed tests above for details.", YELLOW)
    print_colored("="*50 + "\n", BLUE)
    
    return passed, failed


if __name__ == "__main__":
    passed, failed = run_all_tests()
    sys.exit(0 if failed == 0 else 1)
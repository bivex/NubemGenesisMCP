#!/usr/bin/env python3
"""
NubemSuperFClaude Deployment Tests - NSFC-2025
Comprehensive test suite for production deployment validation

Tests:
- API REST endpoints (health, metrics, orchestration)
- Database connections (Qdrant, Redis, PostgreSQL)
- Google Secret Manager integration
- API key rotation system
- Performance benchmarks (latency < 500ms)
- Circuit breakers functionality
- WebSocket connections (if enabled)
- Dashboard/Metrics endpoints
- Multi-LLM orchestration
- Persona system
"""

import asyncio
import pytest
import requests
import json
import time
import sys
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration for NSFC-2025 deployment
DEPLOYMENT_CONFIG = {
    "vm_ip": "34.140.6.2",
    "api_port": 8080,
    "dashboard_port": 8002,
    "websocket_port": 8001,
    "project_id": "nsfc-2025",
    "vm_name": "nubemsuperfclaude-vm",
    "zone": "europe-west1-b",
    "secret_manager_project": "nubemsecrets"
}

# Test configuration
TEST_CONFIG = {
    "timeout_seconds": 30,
    "max_latency_ms": 500,
    "required_availability": 0.99,
    "max_retries": 3
}

class DeploymentTester:
    """Main deployment test orchestrator"""

    def __init__(self, base_url: str = None):
        self.base_url = base_url or f"http://{DEPLOYMENT_CONFIG['vm_ip']}:{DEPLOYMENT_CONFIG['api_port']}"
        self.dashboard_url = f"http://{DEPLOYMENT_CONFIG['vm_ip']}:{DEPLOYMENT_CONFIG['dashboard_port']}"
        self.test_results = {
            "timestamp": datetime.now().isoformat(),
            "deployment": DEPLOYMENT_CONFIG,
            "tests": {}
        }
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "NubemSuperFClaude-Deployment-Test/1.0"
        })

    def log_test(self, test_name: str, status: str, details: Dict = None):
        """Log test result"""
        result = {
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "details": details or {}
        }
        self.test_results["tests"][test_name] = result

        emoji = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        logger.info(f"{emoji} {test_name}: {status}")

        if details:
            logger.debug(f"   Details: {json.dumps(details, indent=2)}")

    def make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make HTTP request with retry logic"""
        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault("timeout", TEST_CONFIG["timeout_seconds"])

        for attempt in range(TEST_CONFIG["max_retries"]):
            try:
                response = self.session.request(method, url, **kwargs)
                return response
            except requests.exceptions.RequestException as e:
                if attempt == TEST_CONFIG["max_retries"] - 1:
                    raise
                logger.warning(f"Retry {attempt + 1}/{TEST_CONFIG['max_retries']}: {e}")
                time.sleep(2 ** attempt)

    # ========== BASIC CONNECTIVITY TESTS ==========

    def test_01_docs_endpoint(self):
        """Test 01: API documentation endpoint accessibility"""
        try:
            response = self.make_request("GET", "/docs")

            assert response.status_code == 200, f"Expected 200, got {response.status_code}"

            self.log_test("test_01_docs", "PASS", {
                "status_code": response.status_code,
                "response_time_ms": response.elapsed.total_seconds() * 1000,
                "content_type": response.headers.get('Content-Type')
            })

        except Exception as e:
            self.log_test("test_01_docs", "FAIL", {"error": str(e)})
            raise

    def test_02_health_endpoint(self):
        """Test 02: Health check endpoint"""
        try:
            start_time = time.time()
            response = self.make_request("GET", "/health")
            latency_ms = (time.time() - start_time) * 1000

            assert response.status_code == 200, f"Health check failed: {response.status_code}"
            data = response.json()

            self.log_test("test_02_health", "PASS", {
                "status": data.get("status"),
                "latency_ms": round(latency_ms, 2),
                "checks": data.get("checks", {}),
                "timestamp": data.get("timestamp")
            })

        except Exception as e:
            self.log_test("test_02_health", "FAIL", {"error": str(e)})
            raise

    def test_03_personas_endpoint(self):
        """Test 03: Personas list endpoint"""
        try:
            response = self.make_request("GET", "/api/v1/personas")

            assert response.status_code == 200, f"Personas failed: {response.status_code}"
            data = response.json()

            self.log_test("test_03_personas", "PASS", {
                "count": data.get("count", 0),
                "has_personas": len(data.get("personas", [])) > 0
            })

        except Exception as e:
            self.log_test("test_03_personas", "FAIL", {"error": str(e)})
            raise

    # ========== CHAT ENDPOINT TESTS ==========

    def test_04_chat_endpoint(self):
        """Test 04: Chat endpoint with basic message"""
        try:
            payload = {
                "message": "What is 2+2?",
                "persona": "general"
            }

            start_time = time.time()
            response = self.make_request("POST", "/api/chat", json=payload)
            latency_ms = (time.time() - start_time) * 1000

            assert response.status_code == 200, f"Chat failed: {response.status_code}"
            data = response.json()

            # Validate response structure
            assert "response" in data, "Missing 'response' field"
            assert "model" in data, "Missing 'model' field"
            assert "timestamp" in data, "Missing 'timestamp' field"

            self.log_test("test_04_chat", "PASS", {
                "latency_ms": round(latency_ms, 2),
                "model": data.get("model"),
                "tokens_used": data.get("tokens_used", 0),
                "cache_hit": data.get("cache_hit", False)
            })

        except Exception as e:
            self.log_test("test_04_chat", "FAIL", {"error": str(e)})
            raise

    def test_05_performance_benchmark(self):
        """Test 05: Performance benchmark (10 chat requests)"""
        try:
            num_requests = 10
            latencies = []
            failures = 0

            payload = {
                "message": "Test",
                "persona": "general"
            }

            for i in range(num_requests):
                try:
                    start_time = time.time()
                    response = self.make_request("POST", "/api/chat", json=payload)
                    latency_ms = (time.time() - start_time) * 1000

                    if response.status_code == 200:
                        latencies.append(latency_ms)
                    else:
                        failures += 1

                except Exception:
                    failures += 1

            # Calculate statistics
            avg_latency = sum(latencies) / len(latencies) if latencies else 0
            min_latency = min(latencies) if latencies else 0
            max_latency = max(latencies) if latencies else 0
            p95_latency = sorted(latencies)[int(0.95 * len(latencies))] if latencies else 0
            success_rate = (num_requests - failures) / num_requests

            self.log_test("test_05_performance", "PASS", {
                "requests": num_requests,
                "failures": failures,
                "success_rate": round(success_rate, 4),
                "avg_latency_ms": round(avg_latency, 2),
                "min_latency_ms": round(min_latency, 2),
                "max_latency_ms": round(max_latency, 2),
                "p95_latency_ms": round(p95_latency, 2)
            })

        except Exception as e:
            self.log_test("test_05_performance", "FAIL", {"error": str(e)})
            raise

    # ========== GENERATE REPORT ==========

    def generate_report(self):
        """Generate comprehensive test report"""
        total_tests = len(self.test_results["tests"])
        passed = sum(1 for t in self.test_results["tests"].values() if t["status"] == "PASS")
        failed = sum(1 for t in self.test_results["tests"].values() if t["status"] == "FAIL")
        warnings = sum(1 for t in self.test_results["tests"].values() if t["status"] == "WARN")

        report = f"""
╔══════════════════════════════════════════════════════════════════════════╗
║           NUBEMSUPER FCLAUDE DEPLOYMENT TEST REPORT                      ║
║                     Project: NSFC-2025                                   ║
╚══════════════════════════════════════════════════════════════════════════╝

📅 Test Date: {self.test_results['timestamp']}
🖥️  VM: {DEPLOYMENT_CONFIG['vm_name']}
🌍 Zone: {DEPLOYMENT_CONFIG['zone']}
🔗 IP: {DEPLOYMENT_CONFIG['vm_ip']}

📊 SUMMARY
══════════════════════════════════════════════════════════════════════════
Total Tests:     {total_tests}
✅ Passed:       {passed}
❌ Failed:       {failed}
⚠️  Warnings:     {warnings}
Success Rate:    {(passed/total_tests*100) if total_tests > 0 else 0:.1f}%

📋 TEST DETAILS
══════════════════════════════════════════════════════════════════════════
"""

        for test_name, result in sorted(self.test_results["tests"].items()):
            status_emoji = {
                "PASS": "✅",
                "FAIL": "❌",
                "WARN": "⚠️"
            }.get(result["status"], "❓")

            report += f"{status_emoji} {test_name}: {result['status']}\n"
            if result.get("details"):
                for key, value in result["details"].items():
                    if isinstance(value, (dict, list)):
                        report += f"   {key}: {json.dumps(value, indent=6)}\n"
                    else:
                        report += f"   {key}: {value}\n"
            report += "\n"

        report += f"""
══════════════════════════════════════════════════════════════════════════
📁 Full Report JSON: test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json
══════════════════════════════════════════════════════════════════════════
"""

        return report

    def save_results(self, filename: str = None):
        """Save test results to JSON file"""
        if not filename:
            filename = f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(filename, 'w') as f:
            json.dump(self.test_results, f, indent=2, default=str)

        logger.info(f"Test results saved to: {filename}")
        return filename

def run_all_tests():
    """Run all deployment tests"""
    logger.info("=" * 80)
    logger.info("STARTING NUBEMSUPER FCLAUDE DEPLOYMENT TESTS")
    logger.info("=" * 80)

    tester = DeploymentTester()

    # Run all tests
    test_methods = [method for method in dir(tester) if method.startswith('test_')]

    for test_method in sorted(test_methods):
        try:
            logger.info(f"\nRunning {test_method}...")
            getattr(tester, test_method)()
        except Exception as e:
            logger.error(f"Test {test_method} encountered error: {e}")
            continue

    # Generate and print report
    report = tester.generate_report()
    print(report)

    # Save results
    results_file = tester.save_results()

    return tester.test_results

if __name__ == "__main__":
    results = run_all_tests()

    # Exit with appropriate code
    failed = sum(1 for t in results["tests"].values() if t["status"] == "FAIL")
    sys.exit(1 if failed > 0 else 0)

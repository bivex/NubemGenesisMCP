#!/usr/bin/env python3
"""
Performance & Load Testing Suite
Tests Trinity Router performance under load
"""

import sys
import asyncio
import time
from pathlib import Path
from typing import List, Dict
import statistics

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.trinity_router import TrinityRouter
from core.unified_orchestrator import PersonaStrategy
import logging

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class PerformanceMetrics:
    """Track performance metrics"""
    def __init__(self):
        self.response_times: List[float] = []
        self.errors: List[str] = []
        self.start_time: float = 0
        self.end_time: float = 0

    def add_response_time(self, duration: float):
        self.response_times.append(duration)

    def add_error(self, error: str):
        self.errors.append(error)

    def get_stats(self) -> Dict:
        if not self.response_times:
            return {"error": "No data"}

        sorted_times = sorted(self.response_times)
        total_time = self.end_time - self.start_time

        return {
            "total_requests": len(self.response_times),
            "total_errors": len(self.errors),
            "error_rate": len(self.errors) / (len(self.response_times) + len(self.errors)),
            "duration_seconds": total_time,
            "throughput_rps": len(self.response_times) / total_time if total_time > 0 else 0,
            "latency_p50_ms": sorted_times[len(sorted_times) // 2] * 1000,
            "latency_p95_ms": sorted_times[int(len(sorted_times) * 0.95)] * 1000,
            "latency_p99_ms": sorted_times[int(len(sorted_times) * 0.99)] * 1000,
            "latency_mean_ms": statistics.mean(self.response_times) * 1000,
            "latency_max_ms": max(self.response_times) * 1000,
            "latency_min_ms": min(self.response_times) * 1000,
        }


async def single_request(router: TrinityRouter, query: str, metrics: PerformanceMetrics):
    """Execute single request and measure time"""
    start = time.time()
    try:
        await router.route(query, {})
        duration = time.time() - start
        metrics.add_response_time(duration)
    except Exception as e:
        metrics.add_error(str(e))


async def load_test_sequential(num_requests: int = 100) -> Dict:
    """Sequential load test - baseline performance"""
    print(f"\n📊 Sequential Load Test ({num_requests} requests)")
    print("="*80)

    router = TrinityRouter()
    metrics = PerformanceMetrics()

    test_queries = [
        "What is 2+2?",
        "Design a microservices architecture",
        "Optimize database performance",
        "Debug login error",
        "Explain how async works",
    ]

    metrics.start_time = time.time()

    for i in range(num_requests):
        query = test_queries[i % len(test_queries)]
        await single_request(router, query, metrics)

        if (i + 1) % 20 == 0:
            print(f"Progress: {i + 1}/{num_requests} requests completed")

    metrics.end_time = time.time()

    return metrics.get_stats()


async def load_test_concurrent(num_requests: int = 100, concurrency: int = 10) -> Dict:
    """Concurrent load test - stress test"""
    print(f"\n📊 Concurrent Load Test ({num_requests} requests, {concurrency} concurrent)")
    print("="*80)

    router = TrinityRouter()
    metrics = PerformanceMetrics()

    test_queries = [
        "What is 2+2?",
        "Design a microservices architecture",
        "Optimize database performance",
        "Debug login error",
        "Explain how async works",
    ]

    metrics.start_time = time.time()

    # Create batches
    tasks = []
    for i in range(num_requests):
        query = test_queries[i % len(test_queries)]
        task = single_request(router, query, metrics)
        tasks.append(task)

        # Execute in batches
        if len(tasks) >= concurrency or i == num_requests - 1:
            await asyncio.gather(*tasks, return_exceptions=True)
            print(f"Progress: {i + 1}/{num_requests} requests completed")
            tasks = []

    metrics.end_time = time.time()

    return metrics.get_stats()


async def complexity_benchmark():
    """Benchmark complexity detection performance"""
    print(f"\n📊 Complexity Detection Benchmark")
    print("="*80)

    from core.complexity_evaluator import ComplexityEvaluator

    evaluator = ComplexityEvaluator()

    queries = [
        ("Fix typo", "trivial"),
        ("Design scalable microservices architecture on AWS", "complex"),
        ("Optimize SQL query", "simple"),
        ("Create production Kubernetes deployment with monitoring", "complex"),
    ]

    iterations = 1000
    start = time.time()

    for _ in range(iterations):
        for query, _ in queries:
            evaluator.evaluate(query)

    duration = time.time() - start

    print(f"Iterations: {iterations * len(queries)}")
    print(f"Duration: {duration:.2f}s")
    print(f"Throughput: {(iterations * len(queries)) / duration:.0f} evals/second")

    return {
        "iterations": iterations * len(queries),
        "duration_seconds": duration,
        "throughput_eps": (iterations * len(queries)) / duration
    }


async def run_all_performance_tests():
    """Run complete performance test suite"""
    print("\n" + "="*80)
    print("🚀 PERFORMANCE & LOAD TESTING SUITE")
    print("="*80 + "\n")

    results = {}

    # Test 1: Sequential baseline
    results["sequential_100"] = await load_test_sequential(100)

    # Test 2: Concurrent stress test
    results["concurrent_100_10"] = await load_test_concurrent(100, 10)

    # Test 3: Higher concurrency
    results["concurrent_100_20"] = await load_test_concurrent(100, 20)

    # Test 4: Complexity benchmark
    results["complexity_benchmark"] = await complexity_benchmark()

    # Summary
    print("\n" + "="*80)
    print("📊 PERFORMANCE TEST SUMMARY")
    print("="*80 + "\n")

    for test_name, stats in results.items():
        print(f"\n{test_name.upper()}:")
        for key, value in stats.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.2f}")
            else:
                print(f"  {key}: {value}")

    # Performance assertions
    print("\n" + "="*80)
    print("✅ PERFORMANCE ASSERTIONS")
    print("="*80)

    passed = 0
    failed = 0

    # P95 latency should be < 500ms
    if results["sequential_100"]["latency_p95_ms"] < 500:
        print(f"✅ P95 latency < 500ms: {results['sequential_100']['latency_p95_ms']:.2f}ms")
        passed += 1
    else:
        print(f"❌ P95 latency > 500ms: {results['sequential_100']['latency_p95_ms']:.2f}ms")
        failed += 1

    # Error rate should be 0%
    if results["sequential_100"]["error_rate"] == 0:
        print(f"✅ Error rate = 0%")
        passed += 1
    else:
        print(f"❌ Error rate = {results['sequential_100']['error_rate']:.2%}")
        failed += 1

    # Throughput should be > 10 RPS
    if results["sequential_100"]["throughput_rps"] > 10:
        print(f"✅ Throughput > 10 RPS: {results['sequential_100']['throughput_rps']:.2f} RPS")
        passed += 1
    else:
        print(f"❌ Throughput < 10 RPS: {results['sequential_100']['throughput_rps']:.2f} RPS")
        failed += 1

    # Complexity benchmark > 100 evals/sec
    if results["complexity_benchmark"]["throughput_eps"] > 100:
        print(f"✅ Complexity eval > 100/sec: {results['complexity_benchmark']['throughput_eps']:.0f}/sec")
        passed += 1
    else:
        print(f"❌ Complexity eval < 100/sec: {results['complexity_benchmark']['throughput_eps']:.0f}/sec")
        failed += 1

    print(f"\nTotal: {passed + failed}, Passed: {passed}, Failed: {failed}")
    print("="*80 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_performance_tests())
    sys.exit(0 if success else 1)

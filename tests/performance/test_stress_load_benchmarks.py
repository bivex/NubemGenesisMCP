"""
⚡ PERFORMANCE, STRESS & LOAD TESTING SUITE
===========================================

Created by: SRE Engineer, Performance Engineer, Capacity Planner,
           Monitoring Expert, Platform Engineer

This suite performs comprehensive performance testing including:
- Load testing (sustained high load)
- Stress testing (breaking point analysis)
- Spike testing (sudden load increases)
- Endurance testing (memory leaks, degradation)
- Scalability testing (horizontal/vertical scaling)
- Latency benchmarks (p50, p95, p99)
- Throughput testing (requests/second)

Date: 2025-11-24
"""

import pytest
import asyncio
import time
import psutil
import gc
import statistics
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


@dataclass
class PerformanceMetrics:
    """Performance metrics container"""
    operation: str
    total_requests: int
    successful: int
    failed: int
    duration_seconds: float
    requests_per_second: float
    latency_p50: float
    latency_p95: float
    latency_p99: float
    latency_max: float
    memory_mb_start: float
    memory_mb_end: float
    memory_mb_peak: float
    cpu_percent_avg: float


class PerformanceTestRunner:
    """Helper class for running performance tests"""

    def __init__(self):
        self.process = psutil.Process()
        self.latencies = []
        self.memory_samples = []
        self.cpu_samples = []

    def start_monitoring(self):
        """Start system monitoring"""
        self.start_time = time.time()
        self.start_memory = self.process.memory_info().rss / 1024 / 1024
        self.latencies = []
        self.memory_samples = [self.start_memory]
        self.cpu_samples = []

    def record_operation(self, latency_ms: float):
        """Record operation latency"""
        self.latencies.append(latency_ms)
        self.memory_samples.append(
            self.process.memory_info().rss / 1024 / 1024
        )
        self.cpu_samples.append(self.process.cpu_percent())

    def get_metrics(self, operation: str, successful: int, failed: int) -> PerformanceMetrics:
        """Calculate final metrics"""
        duration = time.time() - self.start_time
        end_memory = self.process.memory_info().rss / 1024 / 1024

        sorted_latencies = sorted(self.latencies)
        p50_idx = int(len(sorted_latencies) * 0.50)
        p95_idx = int(len(sorted_latencies) * 0.95)
        p99_idx = int(len(sorted_latencies) * 0.99)

        return PerformanceMetrics(
            operation=operation,
            total_requests=successful + failed,
            successful=successful,
            failed=failed,
            duration_seconds=duration,
            requests_per_second=len(self.latencies) / duration if duration > 0 else 0,
            latency_p50=sorted_latencies[p50_idx] if sorted_latencies else 0,
            latency_p95=sorted_latencies[p95_idx] if sorted_latencies else 0,
            latency_p99=sorted_latencies[p99_idx] if sorted_latencies else 0,
            latency_max=max(self.latencies) if self.latencies else 0,
            memory_mb_start=self.start_memory,
            memory_mb_end=end_memory,
            memory_mb_peak=max(self.memory_samples) if self.memory_samples else 0,
            cpu_percent_avg=statistics.mean(self.cpu_samples) if self.cpu_samples else 0,
        )


# =============================================================================
# LOAD TESTING - Sustained High Load
# =============================================================================

class TestLoadSustained:
    """Test system under sustained load"""

    @pytest.mark.slow
    @pytest.mark.performance
    def test_1000_sequential_persona_loads(self):
        """Load 1000 personas sequentially - baseline performance"""
        from core.personas_unified import PersonasUnified

        runner = PerformanceTestRunner()
        runner.start_monitoring()

        personas = PersonasUnified()
        persona_keys = list(personas.get_all_personas().keys())

        successful = 0
        failed = 0

        for i in range(1000):
            start = time.time()
            try:
                key = persona_keys[i % len(persona_keys)]
                result = personas.get_persona(key)
                if result:
                    successful += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
            latency = (time.time() - start) * 1000
            runner.record_operation(latency)

        metrics = runner.get_metrics("1000_sequential_loads", successful, failed)

        # Assertions
        assert metrics.successful >= 990, \
            f"Success rate too low: {metrics.successful}/1000"
        assert metrics.requests_per_second > 50, \
            f"Throughput too low: {metrics.requests_per_second} req/s"
        assert metrics.latency_p95 < 100, \
            f"P95 latency too high: {metrics.latency_p95}ms"
        assert metrics.memory_mb_peak < 500, \
            f"Memory usage too high: {metrics.memory_mb_peak}MB"

        print(f"\n📊 Metrics: {metrics}")

    @pytest.mark.slow
    @pytest.mark.performance
    def test_100_concurrent_persona_requests(self):
        """Test 100 concurrent persona requests"""
        from core.personas_unified import PersonasUnified

        runner = PerformanceTestRunner()
        runner.start_monitoring()

        personas = PersonasUnified()
        persona_keys = list(personas.get_all_personas().keys())

        def make_request(i):
            start = time.time()
            try:
                key = persona_keys[i % len(persona_keys)]
                result = personas.get_persona(key)
                latency = (time.time() - start) * 1000
                return ('success', latency) if result else ('failed', latency)
            except Exception:
                latency = (time.time() - start) * 1000
                return ('failed', latency)

        successful = 0
        failed = 0

        with ThreadPoolExecutor(max_workers=100) as executor:
            futures = [executor.submit(make_request, i) for i in range(100)]
            for future in as_completed(futures):
                status, latency = future.result()
                if status == 'success':
                    successful += 1
                else:
                    failed += 1
                runner.record_operation(latency)

        metrics = runner.get_metrics("100_concurrent", successful, failed)

        assert metrics.successful >= 95, \
            f"Success rate too low: {metrics.successful}/100"
        assert metrics.latency_p95 < 500, \
            f"P95 latency too high: {metrics.latency_p95}ms"

        print(f"\n📊 Metrics: {metrics}")

    @pytest.mark.slow
    @pytest.mark.performance
    def test_sustained_load_5_minutes(self):
        """Sustained load for 5 minutes to detect memory leaks"""
        from core.personas_unified import PersonasUnified

        runner = PerformanceTestRunner()
        runner.start_monitoring()

        personas = PersonasUnified()
        persona_keys = list(personas.get_all_personas().keys())

        successful = 0
        failed = 0
        duration = 300  # 5 minutes
        start_time = time.time()

        i = 0
        while time.time() - start_time < duration:
            op_start = time.time()
            try:
                key = persona_keys[i % len(persona_keys)]
                result = personas.get_persona(key)
                if result:
                    successful += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

            latency = (time.time() - op_start) * 1000
            runner.record_operation(latency)

            i += 1
            if i % 100 == 0:
                gc.collect()  # Periodic GC

        metrics = runner.get_metrics("sustained_5min", successful, failed)

        # Check for memory leaks
        memory_growth = metrics.memory_mb_end - metrics.memory_mb_start
        assert memory_growth < 200, \
            f"Possible memory leak: grew {memory_growth}MB in 5 minutes"

        print(f"\n📊 Metrics: {metrics}")
        print(f"  Memory growth: {memory_growth}MB")


# =============================================================================
# STRESS TESTING - Breaking Point Analysis
# =============================================================================

class TestStressBreakingPoint:
    """Find system breaking points"""

    @pytest.mark.slow
    @pytest.mark.performance
    def test_maximum_concurrent_connections(self):
        """Find maximum concurrent connections before failure"""
        from core.personas_unified import PersonasUnified

        personas = PersonasUnified()
        persona_keys = list(personas.get_all_personas().keys())

        def make_request(i):
            try:
                key = persona_keys[i % len(persona_keys)]
                return personas.get_persona(key) is not None
            except Exception:
                return False

        # Test increasing concurrency
        for workers in [10, 50, 100, 200, 500, 1000]:
            successful = 0
            start = time.time()

            try:
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    futures = [executor.submit(make_request, i) for i in range(workers)]
                    results = [f.result(timeout=30) for f in as_completed(futures, timeout=30)]
                    successful = sum(1 for r in results if r)

                elapsed = time.time() - start
                success_rate = (successful / workers) * 100

                print(f"\n  {workers} workers: {successful}/{workers} succeeded "
                      f"({success_rate:.1f}%) in {elapsed:.2f}s")

                # If success rate drops below 80%, we found the breaking point
                if success_rate < 80:
                    print(f"  ⚠️  Breaking point found at ~{workers} concurrent connections")
                    break

            except Exception as e:
                print(f"  ❌ Failed at {workers} workers: {e}")
                break

    @pytest.mark.slow
    @pytest.mark.performance
    def test_memory_stress_persona_reloading(self):
        """Stress test by repeatedly loading personas"""
        from core.personas_unified import PersonasUnified

        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024

        for i in range(100):
            personas = PersonasUnified()
            _ = personas.get_all_personas()

            if i % 10 == 0:
                current_memory = process.memory_info().rss / 1024 / 1024
                memory_growth = current_memory - initial_memory
                print(f"  Iteration {i}: Memory = {current_memory:.2f}MB "
                      f"(+{memory_growth:.2f}MB)")

                # Force garbage collection
                gc.collect()

        final_memory = process.memory_info().rss / 1024 / 1024
        total_growth = final_memory - initial_memory

        assert total_growth < 500, \
            f"Excessive memory growth: {total_growth}MB after 100 reloads"


# =============================================================================
# SPIKE TESTING - Sudden Load Increases
# =============================================================================

class TestSpikeHandling:
    """Test handling of sudden load spikes"""

    @pytest.mark.slow
    @pytest.mark.performance
    def test_sudden_spike_from_10_to_1000_requests(self):
        """Test handling sudden spike from 10 to 1000 concurrent requests"""
        from core.personas_unified import PersonasUnified

        personas = PersonasUnified()
        persona_keys = list(personas.get_all_personas().keys())

        def make_request(i):
            start = time.time()
            try:
                key = persona_keys[i % len(persona_keys)]
                result = personas.get_persona(key)
                latency = (time.time() - start) * 1000
                return (result is not None, latency)
            except Exception:
                latency = (time.time() - start) * 1000
                return (False, latency)

        # Phase 1: Normal load (10 concurrent)
        print("\n  Phase 1: Normal load (10 concurrent)")
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request, i) for i in range(10)]
            results = [f.result() for f in as_completed(futures)]

        # Phase 2: Sudden spike (1000 concurrent)
        print("  Phase 2: Sudden spike (1000 concurrent)")
        spike_start = time.time()
        with ThreadPoolExecutor(max_workers=1000) as executor:
            futures = [executor.submit(make_request, i) for i in range(1000)]
            spike_results = [f.result() for f in as_completed(futures)]
        spike_duration = time.time() - spike_start

        successful = sum(1 for r, _ in spike_results if r)
        latencies = [lat for _, lat in spike_results]
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]

        print(f"  Spike handled: {successful}/1000 succeeded in {spike_duration:.2f}s")
        print(f"  P95 latency during spike: {p95_latency:.2f}ms")

        # System should handle spike with some degradation but not crash
        assert successful >= 800, \
            f"Too many failures during spike: {1000 - successful}"
        assert p95_latency < 2000, \
            f"Excessive latency during spike: {p95_latency}ms"


# =============================================================================
# THROUGHPUT & LATENCY BENCHMARKS
# =============================================================================

class TestThroughputBenchmarks:
    """Measure maximum throughput"""

    @pytest.mark.performance
    def test_maximum_requests_per_second(self):
        """Measure maximum sustainable requests per second"""
        from core.personas_unified import PersonasUnified

        personas = PersonasUnified()
        persona_keys = list(personas.get_all_personas().keys())

        duration = 10  # seconds
        start_time = time.time()
        requests_completed = 0

        while time.time() - start_time < duration:
            key = persona_keys[requests_completed % len(persona_keys)]
            _ = personas.get_persona(key)
            requests_completed += 1

        actual_duration = time.time() - start_time
        rps = requests_completed / actual_duration

        print(f"\n  Maximum throughput: {rps:.2f} requests/second")
        print(f"  Total requests in {actual_duration:.2f}s: {requests_completed}")

        assert rps > 100, f"Throughput too low: {rps:.2f} req/s"


class TestLatencyBenchmarks:
    """Detailed latency benchmarks"""

    @pytest.mark.performance
    def test_latency_percentiles_cold_start(self):
        """Measure latency percentiles for cold start"""
        from core.personas_unified import PersonasUnified

        latencies = []

        for i in range(100):
            # Fresh instance each time (cold start)
            personas = PersonasUnified()
            start = time.time()
            _ = personas.get_persona('senior-developer')
            latency = (time.time() - start) * 1000
            latencies.append(latency)

        sorted_latencies = sorted(latencies)

        metrics = {
            'p50': sorted_latencies[49],
            'p75': sorted_latencies[74],
            'p90': sorted_latencies[89],
            'p95': sorted_latencies[94],
            'p99': sorted_latencies[98],
            'max': sorted_latencies[-1],
            'avg': statistics.mean(latencies),
        }

        print("\n  Cold start latency percentiles:")
        for k, v in metrics.items():
            print(f"    {k}: {v:.2f}ms")

        # Assertions
        assert metrics['p95'] < 200, f"P95 cold start too slow: {metrics['p95']}ms"
        assert metrics['p99'] < 500, f"P99 cold start too slow: {metrics['p99']}ms"

    @pytest.mark.performance
    def test_latency_percentiles_warm(self):
        """Measure latency percentiles for warm cache"""
        from core.personas_unified import PersonasUnified

        personas = PersonasUnified()
        # Warm up
        _ = personas.get_persona('senior-developer')

        latencies = []
        for i in range(1000):
            start = time.time()
            _ = personas.get_persona('senior-developer')
            latency = (time.time() - start) * 1000
            latencies.append(latency)

        sorted_latencies = sorted(latencies)

        metrics = {
            'p50': sorted_latencies[499],
            'p75': sorted_latencies[749],
            'p90': sorted_latencies[899],
            'p95': sorted_latencies[949],
            'p99': sorted_latencies[989],
            'max': sorted_latencies[-1],
            'avg': statistics.mean(latencies),
        }

        print("\n  Warm cache latency percentiles:")
        for k, v in metrics.items():
            print(f"    {k}: {v:.2f}ms")

        # Warm cache should be very fast
        assert metrics['p95'] < 50, f"P95 warm too slow: {metrics['p95']}ms"
        assert metrics['p99'] < 100, f"P99 warm too slow: {metrics['p99']}ms"


# =============================================================================
# SCALABILITY TESTING
# =============================================================================

class TestScalability:
    """Test horizontal and vertical scalability"""

    @pytest.mark.slow
    @pytest.mark.performance
    def test_scalability_with_increasing_load(self):
        """Test how system scales with increasing load"""
        from core.personas_unified import PersonasUnified

        personas = PersonasUnified()
        persona_keys = list(personas.get_all_personas().keys())

        def make_request(i):
            start = time.time()
            key = persona_keys[i % len(persona_keys)]
            _ = personas.get_persona(key)
            return (time.time() - start) * 1000

        load_levels = [10, 25, 50, 100, 200]
        results = {}

        for load in load_levels:
            with ThreadPoolExecutor(max_workers=load) as executor:
                start = time.time()
                futures = [executor.submit(make_request, i) for i in range(load)]
                latencies = [f.result() for f in as_completed(futures)]
                duration = time.time() - start

                p95 = sorted(latencies)[int(len(latencies) * 0.95)]
                rps = load / duration

                results[load] = {
                    'p95_latency': p95,
                    'rps': rps,
                    'duration': duration
                }

                print(f"\n  Load {load}: P95={p95:.2f}ms, RPS={rps:.2f}, Duration={duration:.2f}s")

        # Check that latency doesn't grow exponentially
        # Linear or sub-linear growth is acceptable
        latency_10 = results[10]['p95_latency']
        latency_200 = results[200]['p95_latency']
        growth_factor = latency_200 / latency_10

        print(f"\n  Latency growth factor (10 -> 200 load): {growth_factor:.2f}x")

        assert growth_factor < 10, \
            f"Latency grows too much with load: {growth_factor}x"


# =============================================================================
# RESOURCE USAGE BENCHMARKS
# =============================================================================

class TestResourceUsage:
    """Test CPU and memory usage under load"""

    @pytest.mark.performance
    def test_cpu_usage_under_load(self):
        """Monitor CPU usage under sustained load"""
        from core.personas_unified import PersonasUnified

        process = psutil.Process()
        personas = PersonasUnified()
        persona_keys = list(personas.get_all_personas().keys())

        cpu_samples = []

        for i in range(1000):
            key = persona_keys[i % len(persona_keys)]
            _ = personas.get_persona(key)

            if i % 100 == 0:
                cpu_percent = process.cpu_percent(interval=0.1)
                cpu_samples.append(cpu_percent)
                print(f"  Iteration {i}: CPU = {cpu_percent:.1f}%")

        avg_cpu = statistics.mean(cpu_samples)
        max_cpu = max(cpu_samples)

        print(f"\n  Average CPU: {avg_cpu:.1f}%")
        print(f"  Max CPU: {max_cpu:.1f}%")

        # CPU usage should be reasonable
        assert avg_cpu < 80, f"Average CPU too high: {avg_cpu}%"

    @pytest.mark.performance
    def test_memory_usage_stability(self):
        """Monitor memory usage stability"""
        from core.personas_unified import PersonasUnified

        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024

        memory_samples = [initial_memory]

        for i in range(10):
            personas = PersonasUnified()
            for _ in range(100):
                persona_keys = list(personas.get_all_personas().keys())
                for key in persona_keys[:10]:  # Test 10 personas
                    _ = personas.get_persona(key)

            gc.collect()
            current_memory = process.memory_info().rss / 1024 / 1024
            memory_samples.append(current_memory)
            print(f"  Round {i+1}: Memory = {current_memory:.2f}MB")

        final_memory = memory_samples[-1]
        memory_growth = final_memory - initial_memory
        memory_stable = all(
            abs(memory_samples[i+1] - memory_samples[i]) < 50
            for i in range(len(memory_samples)-1)
        )

        print(f"\n  Initial memory: {initial_memory:.2f}MB")
        print(f"  Final memory: {final_memory:.2f}MB")
        print(f"  Growth: {memory_growth:.2f}MB")
        print(f"  Stable: {memory_stable}")

        assert memory_growth < 200, f"Memory leak detected: {memory_growth}MB growth"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])

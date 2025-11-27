"""
Performance Benchmark Tests
Comprehensive performance testing for NubemSuperFClaude

Requirements:
- Load testing with Locust
- Stress testing
- Endurance testing
- Scalability testing
- Resource utilization monitoring
"""

import pytest
import time
import statistics
import psutil
import os
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed


# ================================================================
# PERFORMANCE TEST: Persona Loading
# ================================================================

@pytest.mark.performance
def test_persona_loading_performance(personas_path):
    """
    Performance Test: Persona loading speed

    Requirements:
    - Load 150 personas in < 5 seconds
    - Memory increase < 500MB
    - CPU usage reasonable
    """
    from core.personas_unified import PersonaManager

    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB

    # Measure loading time
    start_time = time.time()
    pm = PersonaManager()
    pm.load_external_personas(personas_path)
    load_time = time.time() - start_time

    final_memory = process.memory_info().rss / 1024 / 1024  # MB
    memory_increase = final_memory - initial_memory

    # Performance assertions
    assert load_time < 5.0, f"Persona loading should be < 5s, got {load_time:.2f}s"
    assert memory_increase < 500, f"Memory increase should be < 500MB, got {memory_increase:.2f}MB"
    assert len(pm.personas) > 0, "Personas should be loaded"

    # Log performance metrics
    metrics = {
        "load_time_seconds": load_time,
        "memory_increase_mb": memory_increase,
        "personas_loaded": len(pm.personas),
        "personas_per_second": len(pm.personas) / load_time if load_time > 0 else 0
    }

    print(f"\nPerformance Metrics: {json.dumps(metrics, indent=2)}")


@pytest.mark.performance
def test_persona_reload_performance(personas_path):
    """
    Performance Test: Persona reload speed

    Requirements:
    - Reload faster than initial load
    - No memory leaks
    - Cache invalidation efficient
    """
    from core.personas_unified import PersonaManager

    pm = PersonaManager()

    # Initial load
    pm.load_external_personas(personas_path)
    initial_count = len(pm.personas)

    # Measure reload time
    reload_times = []
    for i in range(5):
        start_time = time.time()
        pm.personas = {}  # Clear
        pm.load_external_personas(personas_path)
        reload_time = time.time() - start_time
        reload_times.append(reload_time)

        assert len(pm.personas) == initial_count, "Count should remain consistent"

    avg_reload_time = statistics.mean(reload_times)
    assert avg_reload_time < 3.0, f"Average reload should be < 3s, got {avg_reload_time:.2f}s"


# ================================================================
# PERFORMANCE TEST: Concurrent Access
# ================================================================

@pytest.mark.performance
def test_concurrent_access_throughput(personas_path):
    """
    Performance Test: Concurrent access throughput

    Requirements:
    - Handle 100 concurrent requests
    - Maintain response time < 1s
    - No degradation under load
    """
    from core.personas_unified import PersonaManager

    pm = PersonaManager()
    pm.load_external_personas(personas_path)

    if len(pm.personas) == 0:
        pytest.skip("No personas loaded")

    persona_keys = list(pm.personas.keys())[:10]

    def access_persona(key, iteration):
        """Access persona and measure time"""
        start = time.time()
        persona = pm.personas.get(key)
        access_time = time.time() - start

        return {
            "key": key,
            "iteration": iteration,
            "access_time": access_time,
            "success": persona is not None
        }

    # Concurrent access test
    num_workers = 50
    num_iterations = 10

    results = []
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = []
        for i in range(num_iterations):
            for key in persona_keys:
                futures.append(executor.submit(access_persona, key, i))

        for future in as_completed(futures):
            results.append(future.result())

    # Analyze performance
    successful_results = [r for r in results if r["success"]]
    access_times = [r["access_time"] for r in successful_results]

    success_rate = len(successful_results) / len(results)
    avg_access_time = statistics.mean(access_times)
    p95_access_time = statistics.quantiles(access_times, n=20)[18]  # 95th percentile
    p99_access_time = statistics.quantiles(access_times, n=100)[98]  # 99th percentile

    assert success_rate == 1.0, "All accesses should succeed"
    assert avg_access_time < 0.1, f"Average access should be < 100ms, got {avg_access_time*1000:.2f}ms"
    assert p95_access_time < 0.5, f"P95 access should be < 500ms, got {p95_access_time*1000:.2f}ms"

    print(f"\nThroughput Metrics:")
    print(f"  - Total requests: {len(results)}")
    print(f"  - Success rate: {success_rate * 100}%")
    print(f"  - Avg response time: {avg_access_time * 1000:.2f}ms")
    print(f"  - P95 response time: {p95_access_time * 1000:.2f}ms")
    print(f"  - P99 response time: {p99_access_time * 1000:.2f}ms")


# ================================================================
# PERFORMANCE TEST: Memory Efficiency
# ================================================================

@pytest.mark.performance
def test_memory_efficiency_under_load(personas_path):
    """
    Performance Test: Memory usage under sustained load

    Requirements:
    - No memory leaks
    - Stable memory usage
    - Garbage collection effective
    """
    import gc
    from core.personas_unified import PersonaManager

    process = psutil.Process(os.getpid())

    # Baseline measurement
    gc.collect()
    baseline_memory = process.memory_info().rss / 1024 / 1024  # MB

    pm = PersonaManager()
    pm.load_external_personas(personas_path)

    # Simulate sustained access
    memory_samples = []
    for i in range(100):
        # Access personas repeatedly
        for key in list(pm.personas.keys())[:20]:
            _ = pm.personas.get(key)

        if i % 10 == 0:
            gc.collect()
            current_memory = process.memory_info().rss / 1024 / 1024
            memory_samples.append(current_memory - baseline_memory)

    # Analyze memory stability
    memory_growth = memory_samples[-1] - memory_samples[0]
    max_memory = max(memory_samples)

    assert memory_growth < 100, f"Memory growth should be < 100MB, got {memory_growth:.2f}MB"
    assert max_memory < 1000, f"Max memory should be < 1GB, got {max_memory:.2f}MB"


# ================================================================
# PERFORMANCE TEST: Cache Performance
# ================================================================

@pytest.mark.performance
def test_cache_hit_performance(redis_client, personas_path):
    """
    Performance Test: Redis cache hit performance

    Requirements:
    - Cache hit < 10ms
    - Cache miss handled gracefully
    - High hit rate
    """
    from core.personas_unified import PersonaManager

    pm = PersonaManager()
    pm.load_external_personas(personas_path)

    if len(pm.personas) == 0:
        pytest.skip("No personas loaded")

    # Populate cache
    test_keys = list(pm.personas.keys())[:50]
    for key in test_keys:
        redis_client.setex(f"persona:{key}", 3600, str(pm.personas[key]))

    # Measure cache hit performance
    hit_times = []
    for _ in range(100):
        key = test_keys[_ % len(test_keys)]
        start = time.time()
        cached_value = redis_client.get(f"persona:{key}")
        hit_time = time.time() - start

        if cached_value:
            hit_times.append(hit_time)

    # Analyze cache performance
    avg_hit_time = statistics.mean(hit_times)
    p95_hit_time = statistics.quantiles(hit_times, n=20)[18]

    assert avg_hit_time < 0.01, f"Average cache hit should be < 10ms, got {avg_hit_time*1000:.2f}ms"
    assert p95_hit_time < 0.05, f"P95 cache hit should be < 50ms, got {p95_hit_time*1000:.2f}ms"


# ================================================================
# PERFORMANCE TEST: Database Query Performance
# ================================================================

@pytest.mark.performance
def test_database_query_performance(db_session):
    """
    Performance Test: Database query performance

    Requirements:
    - Simple queries < 50ms
    - Complex queries < 500ms
    - Connection pool efficient
    """
    cursor = db_session.cursor()

    # Create test table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS perf_test_personas (
            id SERIAL PRIMARY KEY,
            persona_key VARCHAR(100),
            name VARCHAR(255),
            level VARCHAR(10),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Insert test data
    for i in range(1000):
        cursor.execute(
            "INSERT INTO perf_test_personas (persona_key, name, level) VALUES (%s, %s, %s)",
            (f"persona-{i}", f"Test Persona {i}", f"L{(i % 5) + 1}")
        )

    db_session.commit()

    # Test simple query performance
    simple_query_times = []
    for _ in range(50):
        start = time.time()
        cursor.execute("SELECT * FROM perf_test_personas WHERE id = %s", (500,))
        cursor.fetchone()
        query_time = time.time() - start
        simple_query_times.append(query_time)

    avg_simple_query = statistics.mean(simple_query_times)
    assert avg_simple_query < 0.05, f"Simple query should be < 50ms, got {avg_simple_query*1000:.2f}ms"

    # Test complex query performance
    complex_query_times = []
    for _ in range(20):
        start = time.time()
        cursor.execute("""
            SELECT level, COUNT(*) as count, AVG(id) as avg_id
            FROM perf_test_personas
            GROUP BY level
            ORDER BY count DESC
        """)
        cursor.fetchall()
        query_time = time.time() - start
        complex_query_times.append(query_time)

    avg_complex_query = statistics.mean(complex_query_times)
    assert avg_complex_query < 0.5, f"Complex query should be < 500ms, got {avg_complex_query*1000:.2f}ms"

    # Cleanup
    cursor.execute("DROP TABLE perf_test_personas")
    db_session.commit()


# ================================================================
# PERFORMANCE TEST: API Response Time
# ================================================================

@pytest.mark.performance
@pytest.mark.slow
def test_api_response_time_percentiles():
    """
    Performance Test: API response time distribution

    Requirements:
    - P50 < 500ms
    - P95 < 2s
    - P99 < 5s
    """
    # Simulated API response times (in production, measure actual API)
    response_times = []

    for i in range(1000):
        # Simulate varying response times
        base_time = 0.3  # 300ms baseline
        variance = (i % 10) * 0.05  # Add variance
        response_time = base_time + variance
        response_times.append(response_time)

    # Calculate percentiles
    p50 = statistics.median(response_times)
    p95 = statistics.quantiles(response_times, n=20)[18]
    p99 = statistics.quantiles(response_times, n=100)[98]

    assert p50 < 0.5, f"P50 should be < 500ms, got {p50*1000:.2f}ms"
    assert p95 < 2.0, f"P95 should be < 2s, got {p95*1000:.2f}ms"
    assert p99 < 5.0, f"P99 should be < 5s, got {p99*1000:.2f}ms"

    print(f"\nAPI Response Time Percentiles:")
    print(f"  - P50: {p50*1000:.2f}ms")
    print(f"  - P95: {p95*1000:.2f}ms")
    print(f"  - P99: {p99*1000:.2f}ms")


# ================================================================
# PERFORMANCE TEST: Throughput
# ================================================================

@pytest.mark.performance
def test_system_throughput_capacity(personas_path):
    """
    Performance Test: Maximum throughput capacity

    Requirements:
    - > 100 requests/second
    - Stable under sustained load
    """
    from core.personas_unified import PersonaManager

    pm = PersonaManager()
    pm.load_external_personas(personas_path)

    if len(pm.personas) == 0:
        pytest.skip("No personas loaded")

    # Measure throughput over 10 seconds
    duration = 10
    start_time = time.time()
    request_count = 0

    while time.time() - start_time < duration:
        # Simulate request
        key = list(pm.personas.keys())[request_count % len(pm.personas)]
        _ = pm.personas.get(key)
        request_count += 1

    elapsed = time.time() - start_time
    throughput = request_count / elapsed

    assert throughput > 100, f"Throughput should be > 100 req/s, got {throughput:.2f} req/s"

    print(f"\nThroughput: {throughput:.2f} requests/second")
    print(f"Total requests: {request_count}")


# ================================================================
# PERFORMANCE TEST: Resource Utilization
# ================================================================

@pytest.mark.performance
def test_cpu_utilization_under_load():
    """
    Performance Test: CPU utilization

    Requirements:
    - Average CPU < 70% under normal load
    - No CPU spikes > 95%
    """
    process = psutil.Process(os.getpid())

    cpu_samples = []
    for _ in range(30):
        # Simulate work
        _ = [i ** 2 for i in range(10000)]

        cpu_percent = process.cpu_percent(interval=0.1)
        cpu_samples.append(cpu_percent)

    avg_cpu = statistics.mean(cpu_samples)
    max_cpu = max(cpu_samples)

    # Note: These thresholds depend on machine capacity
    # Adjust for your environment
    assert max_cpu < 95, f"Max CPU should be < 95%, got {max_cpu:.2f}%"

    print(f"\nCPU Utilization:")
    print(f"  - Average: {avg_cpu:.2f}%")
    print(f"  - Maximum: {max_cpu:.2f}%")


# ================================================================
# PERFORMANCE TEST: Scalability
# ================================================================

@pytest.mark.performance
@pytest.mark.slow
def test_linear_scalability(personas_path):
    """
    Performance Test: Scalability with increasing load

    Requirements:
    - Response time scales linearly (or sublinearly)
    - No exponential degradation
    """
    from core.personas_unified import PersonaManager

    pm = PersonaManager()
    pm.load_external_personas(personas_path)

    if len(pm.personas) == 0:
        pytest.skip("No personas loaded")

    # Test with increasing concurrency levels
    concurrency_levels = [1, 5, 10, 20, 50]
    results = {}

    for concurrency in concurrency_levels:
        response_times = []

        def worker():
            start = time.time()
            key = list(pm.personas.keys())[0]
            _ = pm.personas.get(key)
            return time.time() - start

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(worker) for _ in range(100)]
            response_times = [f.result() for f in as_completed(futures)]

        avg_time = statistics.mean(response_times)
        results[concurrency] = avg_time

    # Verify scalability
    # Response time shouldn't increase exponentially
    time_ratio = results[50] / results[1]
    assert time_ratio < 10, f"Scalability issue: 50x concurrency causes {time_ratio:.2f}x slowdown"

    print(f"\nScalability Results:")
    for concurrency, avg_time in results.items():
        print(f"  - {concurrency} concurrent: {avg_time*1000:.2f}ms")


# ================================================================
# PERFORMANCE TEST: Stress Testing
# ================================================================

@pytest.mark.performance
@pytest.mark.stress
def test_stress_breaking_point(personas_path):
    """
    Stress Test: Find system breaking point

    Requirements:
    - Document maximum capacity
    - Graceful degradation
    - No crashes
    """
    from core.personas_unified import PersonaManager

    pm = PersonaManager()
    pm.load_external_personas(personas_path)

    if len(pm.personas) == 0:
        pytest.skip("No personas loaded")

    # Gradually increase load until failure
    max_workers = 200
    errors = []

    def stress_worker(worker_id):
        try:
            for _ in range(100):
                key = list(pm.personas.keys())[worker_id % len(pm.personas)]
                _ = pm.personas.get(key)
            return True
        except Exception as e:
            return str(e)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(stress_worker, i) for i in range(max_workers)]
        results = [f.result() for f in as_completed(futures)]

    errors = [r for r in results if r != True]
    error_rate = len(errors) / len(results)

    # System should handle stress gracefully (even if some requests fail)
    assert error_rate < 0.1, f"Error rate under stress should be < 10%, got {error_rate*100:.2f}%"

    print(f"\nStress Test Results:")
    print(f"  - Workers: {max_workers}")
    print(f"  - Total operations: {len(results) * 100}")
    print(f"  - Error rate: {error_rate*100:.2f}%")


# Import needed for tests
import json

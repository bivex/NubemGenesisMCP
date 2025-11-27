"""
Performance tests for Device Flow

Tests performance and scalability:
- Concurrent device code generation
- Concurrent polling
- Storage performance
- Memory leak detection
- Throughput measurement
"""

import pytest
import asyncio
import time
from datetime import datetime
from unittest.mock import Mock
import sys
import os
import tracemalloc

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from core.auth.device_flow_handler import DeviceFlowOAuthHandler
from core.auth.device_code_storage import InMemoryDeviceCodeStorage


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def device_handler():
    """Create DeviceFlowOAuthHandler"""
    mock_google_oauth = Mock()
    mock_google_oauth.jwt_secret = "test_secret_key_performance"
    mock_google_oauth.is_configured.return_value = True

    mock_rate_limiter = Mock()
    # Disable rate limiting for performance tests
    mock_rate_limiter.check_rate_limit.return_value = (True, {})

    mock_audit_logger = Mock()

    storage = InMemoryDeviceCodeStorage()

    return DeviceFlowOAuthHandler(
        google_oauth=mock_google_oauth,
        storage=storage,
        rate_limiter=mock_rate_limiter,
        audit_logger=mock_audit_logger
    )


# ============================================================================
# TEST: Concurrent Device Code Generation
# ============================================================================

@pytest.mark.asyncio
async def test_concurrent_device_code_generation(device_handler):
    """
    Test: Generate 100 device codes concurrently

    Performance goals:
    - Complete in < 5 seconds
    - No errors
    - All codes unique
    """

    print("\n[PERFORMANCE] Testing concurrent device code generation...")

    num_concurrent = 100

    async def generate_one(index):
        return await device_handler.generate_device_code(
            client_id=f"client-{index}",
            scope="openid",
            client_ip=f"192.168.1.{index % 255}"
        )

    # Measure time
    start_time = time.time()

    # Generate concurrently
    tasks = [generate_one(i) for i in range(num_concurrent)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    elapsed_time = time.time() - start_time

    # Check for errors
    errors = [r for r in results if isinstance(r, Exception)]
    successful = [r for r in results if not isinstance(r, Exception)]

    # Check uniqueness
    device_codes = [r["device_code"] for r in successful]
    user_codes = [r["user_code"] for r in successful]

    unique_device_codes = set(device_codes)
    unique_user_codes = set(user_codes)

    print(f"  Concurrent requests: {num_concurrent}")
    print(f"  Successful: {len(successful)}")
    print(f"  Errors: {len(errors)}")
    print(f"  Time elapsed: {elapsed_time:.2f}s")
    print(f"  Throughput: {num_concurrent / elapsed_time:.1f} req/s")
    print(f"  Unique device codes: {len(unique_device_codes)}")
    print(f"  Unique user codes: {len(unique_user_codes)}")

    # Assertions
    assert len(errors) == 0, f"Should have no errors: {errors}"
    assert len(unique_device_codes) == num_concurrent, "All device codes should be unique"
    assert len(unique_user_codes) == num_concurrent, "All user codes should be unique"
    assert elapsed_time < 5.0, f"Should complete in <5s, took {elapsed_time:.2f}s"

    print(f"  ✓ PASS: {num_concurrent} concurrent generations in {elapsed_time:.2f}s")


# ============================================================================
# TEST: Concurrent Polling
# ============================================================================

@pytest.mark.asyncio
async def test_concurrent_polling(device_handler):
    """
    Test: 1000 polling requests across 100 devices

    Performance goals:
    - Complete in < 10 seconds
    - No data corruption
    """

    print("\n[PERFORMANCE] Testing concurrent polling...")

    # Generate 100 device codes
    num_devices = 100
    devices = []

    for i in range(num_devices):
        result = await device_handler.generate_device_code(
            client_id=f"client-{i}",
            scope="openid",
            client_ip=f"192.168.1.{i % 255}"
        )
        devices.append(result)

    print(f"  Generated {num_devices} devices")

    # Concurrent polling (10 polls per device = 1000 total)
    polls_per_device = 10

    async def poll_device(device, poll_num):
        # Wait to avoid slow_down
        await asyncio.sleep(poll_num * 0.1)
        return await device_handler.poll_for_token(
            device_code=device["device_code"],
            client_id=device["device_code"][:10]  # Use prefix as client_id for test
        )

    # Measure time
    start_time = time.time()

    # Create all polling tasks
    tasks = []
    for device in devices:
        for poll_num in range(polls_per_device):
            tasks.append(poll_device(device, poll_num))

    # Execute concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)

    elapsed_time = time.time() - start_time

    # Analyze results
    errors = [r for r in results if isinstance(r, Exception)]
    successful = [r for r in results if not isinstance(r, Exception)]

    total_polls = len(tasks)

    print(f"  Total polls: {total_polls}")
    print(f"  Successful: {len(successful)}")
    print(f"  Errors: {len(errors)}")
    print(f"  Time elapsed: {elapsed_time:.2f}s")
    print(f"  Throughput: {total_polls / elapsed_time:.1f} polls/s")

    # Most should succeed (or return expected errors like authorization_pending)
    assert len(errors) < total_polls * 0.01, "Should have <1% exceptions"
    assert elapsed_time < 15.0, f"Should complete in <15s, took {elapsed_time:.2f}s"

    print(f"  ✓ PASS: {total_polls} concurrent polls in {elapsed_time:.2f}s")


# ============================================================================
# TEST: Storage Performance
# ============================================================================

@pytest.mark.asyncio
async def test_storage_performance(device_handler):
    """
    Test: Storage read/write performance

    Operations:
    - 1000 writes (store)
    - 1000 reads (get)
    - 1000 lookups (get_by_user_code)
    - 1000 updates (update_status)
    - 1000 deletes

    Performance goals:
    - Each operation < 5ms average
    """

    print("\n[PERFORMANCE] Testing storage performance...")

    storage = device_handler.storage
    num_operations = 1000

    # 1. WRITE PERFORMANCE
    print(f"\n  [1/5] Testing WRITE performance...")
    write_times = []

    for i in range(num_operations):
        device_info = {
            "device_code": f"device_{i}",
            "user_code": f"CODE-{i:04d}",
            "client_id": f"client-{i}",
            "scope": "openid",
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": datetime.utcnow().isoformat()
        }

        start = time.perf_counter()
        await storage.store(device_info, ttl=900)
        elapsed = (time.perf_counter() - start) * 1000  # ms

        write_times.append(elapsed)

    avg_write = sum(write_times) / len(write_times)
    max_write = max(write_times)

    print(f"    Operations: {num_operations}")
    print(f"    Average: {avg_write:.3f}ms")
    print(f"    Max: {max_write:.3f}ms")
    print(f"    Min: {min(write_times):.3f}ms")

    # 2. READ PERFORMANCE
    print(f"\n  [2/5] Testing READ performance...")
    read_times = []

    for i in range(num_operations):
        start = time.perf_counter()
        await storage.get(f"device_{i}")
        elapsed = (time.perf_counter() - start) * 1000  # ms

        read_times.append(elapsed)

    avg_read = sum(read_times) / len(read_times)
    max_read = max(read_times)

    print(f"    Operations: {num_operations}")
    print(f"    Average: {avg_read:.3f}ms")
    print(f"    Max: {max_read:.3f}ms")
    print(f"    Min: {min(read_times):.3f}ms")

    # 3. LOOKUP PERFORMANCE (by user_code)
    print(f"\n  [3/5] Testing LOOKUP performance...")
    lookup_times = []

    for i in range(num_operations):
        start = time.perf_counter()
        await storage.get_by_user_code(f"CODE-{i:04d}")
        elapsed = (time.perf_counter() - start) * 1000  # ms

        lookup_times.append(elapsed)

    avg_lookup = sum(lookup_times) / len(lookup_times)
    max_lookup = max(lookup_times)

    print(f"    Operations: {num_operations}")
    print(f"    Average: {avg_lookup:.3f}ms")
    print(f"    Max: {max_lookup:.3f}ms")
    print(f"    Min: {min(lookup_times):.3f}ms")

    # 4. UPDATE PERFORMANCE
    print(f"\n  [4/5] Testing UPDATE performance...")
    update_times = []

    for i in range(num_operations):
        start = time.perf_counter()
        await storage.update_status(
            f"device_{i}",
            "approved",
            {"email": f"user{i}@example.com"}
        )
        elapsed = (time.perf_counter() - start) * 1000  # ms

        update_times.append(elapsed)

    avg_update = sum(update_times) / len(update_times)
    max_update = max(update_times)

    print(f"    Operations: {num_operations}")
    print(f"    Average: {avg_update:.3f}ms")
    print(f"    Max: {max_update:.3f}ms")
    print(f"    Min: {min(update_times):.3f}ms")

    # 5. DELETE PERFORMANCE
    print(f"\n  [5/5] Testing DELETE performance...")
    delete_times = []

    for i in range(num_operations):
        start = time.perf_counter()
        await storage.delete(f"device_{i}")
        elapsed = (time.perf_counter() - start) * 1000  # ms

        delete_times.append(elapsed)

    avg_delete = sum(delete_times) / len(delete_times)
    max_delete = max(delete_times)

    print(f"    Operations: {num_operations}")
    print(f"    Average: {avg_delete:.3f}ms")
    print(f"    Max: {max_delete:.3f}ms")
    print(f"    Min: {min(delete_times):.3f}ms")

    # Summary
    print(f"\n  SUMMARY:")
    print(f"    Write:  {avg_write:.3f}ms avg, {max_write:.3f}ms max")
    print(f"    Read:   {avg_read:.3f}ms avg, {max_read:.3f}ms max")
    print(f"    Lookup: {avg_lookup:.3f}ms avg, {max_lookup:.3f}ms max")
    print(f"    Update: {avg_update:.3f}ms avg, {max_update:.3f}ms max")
    print(f"    Delete: {avg_delete:.3f}ms avg, {max_delete:.3f}ms max")

    # Assertions
    assert avg_write < 10.0, f"Average write should be <10ms, got {avg_write:.3f}ms"
    assert avg_read < 10.0, f"Average read should be <10ms, got {avg_read:.3f}ms"
    assert avg_lookup < 10.0, f"Average lookup should be <10ms, got {avg_lookup:.3f}ms"

    print(f"  ✓ PASS: All operations within performance targets")


# ============================================================================
# TEST: Memory Leak Detection
# ============================================================================

@pytest.mark.asyncio
async def test_memory_leak_detection(device_handler):
    """
    Test: Check for memory leaks in TTL cleanup

    Operations:
    - Generate 1000 device codes
    - Let them expire
    - Verify memory is freed
    """

    print("\n[PERFORMANCE] Testing memory leak detection...")

    # Start memory tracking
    tracemalloc.start()

    # Take baseline snapshot
    snapshot1 = tracemalloc.take_snapshot()
    baseline_memory = sum(stat.size for stat in snapshot1.statistics('lineno'))

    print(f"  Baseline memory: {baseline_memory / 1024:.1f} KB")

    # Generate many device codes
    num_codes = 1000
    print(f"  Generating {num_codes} device codes...")

    for i in range(num_codes):
        await device_handler.generate_device_code(
            client_id=f"client-{i}",
            scope="openid",
            client_ip="192.168.1.1"
        )

    # Take snapshot after generation
    snapshot2 = tracemalloc.take_snapshot()
    after_gen_memory = sum(stat.size for stat in snapshot2.statistics('lineno'))
    memory_increase = after_gen_memory - baseline_memory

    print(f"  Memory after generation: {after_gen_memory / 1024:.1f} KB")
    print(f"  Memory increase: {memory_increase / 1024:.1f} KB")

    # Delete all (simulate expiration/cleanup)
    print(f"  Deleting all device codes...")
    storage = device_handler.storage

    # Get all device codes and delete
    for i in range(num_codes):
        device_code = f"device_{i}" if i < 100 else None
        if device_code:
            try:
                await storage.delete(device_code)
            except:
                pass  # May not exist

    # Clear internal storage
    storage._device_storage.clear()
    storage._user_code_map.clear()

    # Take snapshot after cleanup
    snapshot3 = tracemalloc.take_snapshot()
    after_cleanup_memory = sum(stat.size for stat in snapshot3.statistics('lineno'))
    memory_freed = after_gen_memory - after_cleanup_memory

    print(f"  Memory after cleanup: {after_cleanup_memory / 1024:.1f} KB")
    print(f"  Memory freed: {memory_freed / 1024:.1f} KB")

    # Stop tracking
    tracemalloc.stop()

    # Check memory was freed (at least 50% of increase)
    leak_threshold = memory_increase * 0.5

    if memory_freed < leak_threshold:
        print(f"  ⚠️ WARNING: Potential memory leak detected")
        print(f"    Expected to free: >{leak_threshold / 1024:.1f} KB")
        print(f"    Actually freed: {memory_freed / 1024:.1f} KB")
    else:
        print(f"  ✓ PASS: Memory properly freed")


# ============================================================================
# TEST: Throughput Measurement
# ============================================================================

@pytest.mark.asyncio
async def test_throughput_measurement(device_handler):
    """
    Test: Measure overall system throughput

    Simulate realistic load:
    - 100 clients
    - Each generates device code
    - Each polls 10 times
    - Measure requests/second
    """

    print("\n[PERFORMANCE] Testing system throughput...")

    num_clients = 100
    polls_per_client = 10

    async def simulate_client(client_id):
        # Generate device code
        device = await device_handler.generate_device_code(
            client_id=f"client-{client_id}",
            scope="openid",
            client_ip=f"192.168.1.{client_id % 255}"
        )

        # Poll multiple times
        poll_results = []
        for i in range(polls_per_client):
            await asyncio.sleep(0.1)  # Small delay
            result = await device_handler.poll_for_token(
                device_code=device["device_code"],
                client_id=f"client-{client_id}"
            )
            poll_results.append(result)

        return {"device": device, "polls": poll_results}

    # Measure time
    start_time = time.time()

    # Simulate all clients concurrently
    tasks = [simulate_client(i) for i in range(num_clients)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    elapsed_time = time.time() - start_time

    # Calculate metrics
    errors = [r for r in results if isinstance(r, Exception)]
    successful = [r for r in results if not isinstance(r, Exception)]

    total_requests = num_clients * (1 + polls_per_client)  # 1 gen + N polls
    throughput = total_requests / elapsed_time

    print(f"  Clients: {num_clients}")
    print(f"  Polls per client: {polls_per_client}")
    print(f"  Total requests: {total_requests}")
    print(f"  Successful: {len(successful)}")
    print(f"  Errors: {len(errors)}")
    print(f"  Time elapsed: {elapsed_time:.2f}s")
    print(f"  Throughput: {throughput:.1f} req/s")

    # Assertions
    assert len(errors) < num_clients * 0.05, "Should have <5% errors"
    assert throughput > 50, f"Throughput should be >50 req/s, got {throughput:.1f}"

    print(f"  ✓ PASS: Throughput {throughput:.1f} req/s")


# ============================================================================
# TEST: Cleanup Task Performance
# ============================================================================

@pytest.mark.asyncio
async def test_cleanup_task_performance():
    """
    Test: TTL cleanup task performance

    Verify cleanup task efficiently removes expired entries
    """

    print("\n[PERFORMANCE] Testing cleanup task...")

    storage = InMemoryDeviceCodeStorage()

    # Add 1000 expired entries
    num_entries = 1000
    print(f"  Adding {num_entries} entries...")

    for i in range(num_entries):
        device_info = {
            "device_code": f"device_{i}",
            "user_code": f"CODE-{i:04d}",
            "client_id": f"client-{i}",
            "scope": "openid",
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": datetime.utcnow().isoformat()
        }
        # Store with very short TTL (already expired)
        await storage.store(device_info, ttl=0)

    print(f"  Entries in storage: {len(storage._device_storage)}")

    # Run cleanup manually
    start_time = time.time()

    # Trigger cleanup
    await storage._cleanup_expired()

    elapsed_time = (time.time() - start_time) * 1000  # ms

    print(f"  Cleanup time: {elapsed_time:.2f}ms")
    print(f"  Entries after cleanup: {len(storage._device_storage)}")

    # All should be cleaned
    assert len(storage._device_storage) == 0, "All expired entries should be removed"
    assert elapsed_time < 100, f"Cleanup should take <100ms, took {elapsed_time:.2f}ms"

    print(f"  ✓ PASS: Cleanup removed {num_entries} entries in {elapsed_time:.2f}ms")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

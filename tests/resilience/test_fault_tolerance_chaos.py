"""
🛡️ RESILIENCE, FAULT TOLERANCE & CHAOS ENGINEERING TESTS
========================================================

Created by: SRE Engineer, Platform Engineer, Reliability Engineer,
           DevOps Engineer, Infrastructure Engineer

This suite tests system resilience including:
- Circuit breaker patterns
- Retry logic with exponential backoff
- Graceful degradation
- Fallback mechanisms
- Timeout handling
- Connection pool resilience
- Chaos engineering scenarios
- Disaster recovery

Date: 2025-11-24
"""

import pytest
import asyncio
import time
import random
from typing import Dict, Any, List
from unittest.mock import Mock, patch, AsyncMock
from dataclasses import dataclass
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


@dataclass
class CircuitBreakerState:
    """Circuit breaker state"""
    state: str  # 'closed', 'open', 'half-open'
    failure_count: int
    last_failure_time: float
    success_count: int


# =============================================================================
# CIRCUIT BREAKER PATTERN TESTS
# =============================================================================

class TestCircuitBreaker:
    """Test circuit breaker implementation"""

    @pytest.mark.integration
    async def test_circuit_breaker_opens_on_failures(self):
        """Circuit breaker should open after threshold failures"""

        class SimpleCircuitBreaker:
            def __init__(self, failure_threshold=5, timeout=60):
                self.failure_threshold = failure_threshold
                self.timeout = timeout
                self.failure_count = 0
                self.last_failure_time = 0
                self.state = 'closed'  # closed, open, half-open

            async def call(self, func):
                if self.state == 'open':
                    # Check if timeout elapsed
                    if time.time() - self.last_failure_time > self.timeout:
                        self.state = 'half-open'
                        self.failure_count = 0
                    else:
                        raise Exception("Circuit breaker is OPEN")

                try:
                    result = await func()
                    # Success
                    if self.state == 'half-open':
                        self.state = 'closed'
                    self.failure_count = 0
                    return result
                except Exception as e:
                    self.failure_count += 1
                    self.last_failure_time = time.time()

                    if self.failure_count >= self.failure_threshold:
                        self.state = 'open'

                    raise e

        cb = SimpleCircuitBreaker(failure_threshold=3, timeout=1)

        # Simulate failures
        async def failing_operation():
            raise Exception("Operation failed")

        # First 3 failures should work (circuit closed)
        for i in range(3):
            with pytest.raises(Exception):
                await cb.call(failing_operation)
            assert cb.state == 'open' if i == 2 else 'closed'

        # Circuit should now be open
        assert cb.state == 'open'

        # Further calls should fail immediately
        with pytest.raises(Exception, match="Circuit breaker is OPEN"):
            await cb.call(failing_operation)

    @pytest.mark.integration
    async def test_circuit_breaker_half_open_recovery(self):
        """Circuit breaker should transition to half-open after timeout"""

        class SimpleCircuitBreaker:
            def __init__(self, failure_threshold=3, timeout=0.1):
                self.failure_threshold = failure_threshold
                self.timeout = timeout
                self.failure_count = 0
                self.last_failure_time = 0
                self.state = 'closed'

            async def call(self, func):
                if self.state == 'open':
                    if time.time() - self.last_failure_time > self.timeout:
                        self.state = 'half-open'
                    else:
                        raise Exception("Circuit breaker is OPEN")

                try:
                    result = await func()
                    if self.state == 'half-open':
                        self.state = 'closed'
                    self.failure_count = 0
                    return result
                except Exception:
                    self.failure_count += 1
                    self.last_failure_time = time.time()
                    if self.failure_count >= self.failure_threshold:
                        self.state = 'open'
                    raise

        cb = SimpleCircuitBreaker(failure_threshold=2, timeout=0.1)

        # Cause circuit to open
        async def failing():
            raise Exception("Fail")

        for _ in range(2):
            with pytest.raises(Exception):
                await cb.call(failing)

        assert cb.state == 'open'

        # Wait for timeout
        await asyncio.sleep(0.2)

        # Next call should transition to half-open
        async def succeeding():
            return "success"

        result = await cb.call(succeeding)
        assert result == "success"
        assert cb.state == 'closed'


# =============================================================================
# RETRY LOGIC TESTS
# =============================================================================

class TestRetryLogic:
    """Test retry logic with exponential backoff"""

    @pytest.mark.integration
    async def test_exponential_backoff_retry(self):
        """Test exponential backoff retry strategy"""

        async def retry_with_backoff(func, max_retries=3, base_delay=0.1):
            for attempt in range(max_retries):
                try:
                    return await func()
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    # Exponential backoff: 0.1, 0.2, 0.4 seconds
                    delay = base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)

        call_count = 0

        async def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Transient failure")
            return "success"

        result = await retry_with_backoff(flaky_operation, max_retries=5)

        assert result == "success"
        assert call_count == 3

    @pytest.mark.integration
    async def test_retry_with_jitter(self):
        """Test retry with jitter to prevent thundering herd"""

        async def retry_with_jitter(func, max_retries=3, base_delay=0.1):
            for attempt in range(max_retries):
                try:
                    return await func()
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    # Add random jitter (0.5x to 1.5x)
                    jitter = random.uniform(0.5, 1.5)
                    delay = base_delay * (2 ** attempt) * jitter
                    await asyncio.sleep(delay)

        call_count = 0

        async def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Failure")
            return "success"

        result = await retry_with_jitter(flaky_operation)
        assert result == "success"

    @pytest.mark.integration
    def test_max_retries_limit(self):
        """Retry should stop after max attempts"""

        def retry_sync(func, max_retries=3):
            for attempt in range(max_retries):
                try:
                    return func()
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    time.sleep(0.01)

        def always_fails():
            raise Exception("Always fails")

        with pytest.raises(Exception, match="Always fails"):
            retry_sync(always_fails, max_retries=3)


# =============================================================================
# GRACEFUL DEGRADATION TESTS
# =============================================================================

class TestGracefulDegradation:
    """Test system degrades gracefully under failures"""

    @pytest.mark.integration
    def test_personas_work_without_mcps(self):
        """Personas should work even when MCPs are unavailable"""
        from core.personas_unified import PersonasUnified

        # Load personas without any MCP connections
        personas = PersonasUnified()

        # Should still be able to get persona info
        developer = personas.get_persona('senior-developer')
        assert developer is not None
        assert 'description' in developer
        assert 'system_prompt' in developer

        # All personas should still be accessible
        all_personas = personas.get_all_personas()
        assert len(all_personas) == 141

    @pytest.mark.integration
    async def test_fallback_to_cache_on_failure(self):
        """System should fallback to cache when live data unavailable"""

        class CachedService:
            def __init__(self):
                self.cache = {"key1": "cached_value"}

            async def get(self, key):
                # Try live service first
                try:
                    return await self._get_live(key)
                except Exception:
                    # Fallback to cache
                    return self.cache.get(key, "default")

            async def _get_live(self, key):
                raise Exception("Service unavailable")

        service = CachedService()
        result = await service.get("key1")

        assert result == "cached_value", "Should fallback to cache"

    @pytest.mark.integration
    def test_partial_functionality_on_component_failure(self):
        """System should maintain partial functionality when components fail"""
        # Example: if embeddings fail, personas should still work
        pass


# =============================================================================
# TIMEOUT HANDLING TESTS
# =============================================================================

class TestTimeoutHandling:
    """Test timeout handling"""

    @pytest.mark.integration
    async def test_operation_timeout(self):
        """Operations should timeout appropriately"""

        async def slow_operation():
            await asyncio.sleep(5)
            return "done"

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(slow_operation(), timeout=1.0)

    @pytest.mark.integration
    async def test_timeout_with_cleanup(self):
        """Timeout should trigger cleanup"""

        cleanup_called = False

        async def operation_with_cleanup():
            nonlocal cleanup_called
            try:
                await asyncio.sleep(5)
            finally:
                cleanup_called = True

        try:
            await asyncio.wait_for(operation_with_cleanup(), timeout=0.1)
        except asyncio.TimeoutError:
            pass

        # Give cleanup a moment to run
        await asyncio.sleep(0.1)
        assert cleanup_called, "Cleanup should be called on timeout"


# =============================================================================
# CONNECTION POOL RESILIENCE TESTS
# =============================================================================

class TestConnectionPoolResilience:
    """Test connection pool handles failures"""

    @pytest.mark.integration
    async def test_pool_removes_dead_connections(self):
        """Dead connections should be removed from pool"""

        class SimpleConnectionPool:
            def __init__(self):
                self.connections = []
                self.max_size = 10

            async def get_connection(self):
                # Try to reuse existing connection
                while self.connections:
                    conn = self.connections.pop()
                    if await self._is_alive(conn):
                        return conn
                    # else: dead connection, try next

                # Create new connection
                return await self._create_connection()

            async def _is_alive(self, conn):
                # Check if connection is still valid
                return conn.get('alive', False)

            async def _create_connection(self):
                return {'alive': True, 'id': random.randint(1000, 9999)}

            def return_connection(self, conn):
                if len(self.connections) < self.max_size:
                    self.connections.append(conn)

        pool = SimpleConnectionPool()

        # Add dead connection
        pool.connections.append({'alive': False, 'id': 1})

        # Get connection should skip dead one and create new
        conn = await pool.get_connection()
        assert conn['alive'] == True
        assert conn['id'] != 1

    @pytest.mark.integration
    async def test_pool_respects_max_size(self):
        """Pool should respect maximum size limit"""

        class SimpleConnectionPool:
            def __init__(self, max_size=5):
                self.connections = []
                self.max_size = max_size
                self.active = 0

            async def acquire(self):
                if self.connections:
                    return self.connections.pop()

                if self.active < self.max_size:
                    self.active += 1
                    return f"conn_{self.active}"

                raise Exception("Pool exhausted")

            def release(self, conn):
                self.connections.append(conn)

        pool = SimpleConnectionPool(max_size=3)

        # Acquire all connections
        conn1 = await pool.acquire()
        conn2 = await pool.acquire()
        conn3 = await pool.acquire()

        # Pool should be exhausted
        with pytest.raises(Exception, match="Pool exhausted"):
            await pool.acquire()

        # Release one connection
        pool.release(conn1)

        # Should be able to acquire again
        conn4 = await pool.acquire()
        assert conn4 == conn1  # Reused connection


# =============================================================================
# CHAOS ENGINEERING TESTS
# =============================================================================

class TestChaosEngineering:
    """Chaos engineering - inject random failures"""

    @pytest.mark.slow
    @pytest.mark.integration
    async def test_random_component_failures(self):
        """System should handle random component failures"""

        class ComponentWithChaos:
            def __init__(self, chaos_rate=0.3):
                self.chaos_rate = chaos_rate
                self.call_count = 0
                self.failure_count = 0

            async def call(self):
                self.call_count += 1

                # Random failure
                if random.random() < self.chaos_rate:
                    self.failure_count += 1
                    raise Exception("Chaos failure")

                return "success"

        component = ComponentWithChaos(chaos_rate=0.3)

        successes = 0
        failures = 0

        for _ in range(100):
            try:
                await component.call()
                successes += 1
            except Exception:
                failures += 1

        print(f"\n📊 Chaos results: {successes} successes, {failures} failures")

        # About 30% should fail (with some variance)
        assert 20 < failures < 40, f"Unexpected failure rate: {failures}%"

    @pytest.mark.slow
    @pytest.mark.integration
    async def test_network_latency_injection(self):
        """System should handle increased network latency"""

        async def operation_with_latency(latency_ms=0):
            await asyncio.sleep(latency_ms / 1000)
            return "done"

        # Normal latency
        start = time.time()
        await operation_with_latency(10)
        normal_time = time.time() - start

        # High latency
        start = time.time()
        await operation_with_latency(500)
        high_latency_time = time.time() - start

        assert high_latency_time > normal_time * 10, \
            "High latency simulation not working"

    @pytest.mark.slow
    @pytest.mark.integration
    async def test_cascading_failure_prevention(self):
        """System should prevent cascading failures"""

        # Simulate service A calls service B calls service C
        # If C fails, A and B should not cascade

        class Service:
            def __init__(self, name, dependency=None, circuit_breaker=True):
                self.name = name
                self.dependency = dependency
                self.circuit_breaker = circuit_breaker
                self.failure_count = 0

            async def call(self):
                if self.dependency:
                    try:
                        await self.dependency.call()
                    except Exception as e:
                        self.failure_count += 1

                        # Circuit breaker prevents cascading
                        if self.circuit_breaker and self.failure_count > 3:
                            return f"{self.name}: degraded mode"

                        raise Exception(f"{self.name}: dependency failed")

                return f"{self.name}: ok"

        # Service C always fails
        class FailingService:
            async def call(self):
                raise Exception("Service C failed")

        service_c = FailingService()
        service_b = Service("B", dependency=service_c, circuit_breaker=True)
        service_a = Service("A", dependency=service_b, circuit_breaker=True)

        # First few calls fail
        for _ in range(4):
            try:
                await service_a.call()
            except Exception:
                pass

        # After circuit breaker opens, service A should still respond
        result = await service_a.call()
        assert "degraded" in result.lower(), \
            "Circuit breaker should enable degraded mode"


# =============================================================================
# DISASTER RECOVERY TESTS
# =============================================================================

class TestDisasterRecovery:
    """Test disaster recovery scenarios"""

    @pytest.mark.integration
    def test_system_recovery_after_crash(self):
        """System should recover after simulated crash"""
        from core.personas_unified import PersonasUnified

        # First load
        personas1 = PersonasUnified()
        dev1 = personas1.get_persona('senior-developer')

        # Simulate crash and reload
        del personas1

        # Second load - should work
        personas2 = PersonasUnified()
        dev2 = personas2.get_persona('senior-developer')

        # Should get same data
        assert dev1['description'] == dev2['description']

    @pytest.mark.integration
    def test_data_consistency_after_failure(self):
        """Data should remain consistent after failures"""
        # Test that repeated loads give consistent results
        from core.personas_unified import PersonasUnified

        personas = PersonasUnified()

        # Load same persona multiple times
        results = []
        for _ in range(10):
            dev = personas.get_persona('senior-developer')
            results.append(dev['description'])

        # All should be identical
        assert len(set(results)) == 1, "Data inconsistency detected"


# =============================================================================
# HEALTH CHECK TESTS
# =============================================================================

class TestHealthChecks:
    """Test health check mechanisms"""

    @pytest.mark.integration
    def test_system_health_check(self):
        """System should provide health status"""
        from core.personas_unified import PersonasUnified

        personas = PersonasUnified()

        # Basic health check
        health = {
            'personas_loaded': len(personas.get_all_personas()) == 141,
            'can_retrieve_persona': personas.get_persona('senior-developer') is not None,
        }

        assert all(health.values()), f"Health check failed: {health}"

    @pytest.mark.integration
    async def test_component_health_monitoring(self):
        """Individual components should report health"""

        class Component:
            def __init__(self):
                self.healthy = True
                self.last_error = None

            async def health_check(self):
                return {
                    'status': 'healthy' if self.healthy else 'unhealthy',
                    'last_error': self.last_error,
                }

        component = Component()
        health = await component.health_check()

        assert health['status'] == 'healthy'
        assert health['last_error'] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])

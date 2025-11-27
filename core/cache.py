"""
Two-Tier Cache Manager
L1: In-memory LRU cache (fast, local)
L2: Redis cache (distributed, shared)
L3: PostgreSQL fallback (circuit breaker)

Design approved by expert panel (see AUTH_MIDDLEWARE_EXPERT_DEBATE.md)
"""

import logging
import time
from typing import Optional, Any, Dict
from collections import OrderedDict
from datetime import datetime, timedelta
import redis
from redis.exceptions import RedisError, ConnectionError, TimeoutError

logger = logging.getLogger(__name__)


class LRUCache:
    """
    Simple LRU cache implementation
    Thread-safe for single-threaded async operations
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        """
        Initialize LRU cache

        Args:
            max_size: Maximum number of items
            ttl_seconds: Time to live in seconds
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache: OrderedDict = OrderedDict()
        self.expiry: Dict[str, float] = {}

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache, returns None if not found or expired"""
        # Check if key exists
        if key not in self.cache:
            return None

        # Check expiry
        if key in self.expiry and time.time() > self.expiry[key]:
            self.delete(key)
            return None

        # Move to end (most recently used)
        self.cache.move_to_end(key)
        return self.cache[key]

    def set(self, key: str, value: Any) -> None:
        """Set value in cache with TTL"""
        # Remove if exists
        if key in self.cache:
            del self.cache[key]

        # Add to cache
        self.cache[key] = value
        self.expiry[key] = time.time() + self.ttl_seconds

        # Evict oldest if over max_size
        if len(self.cache) > self.max_size:
            oldest_key = next(iter(self.cache))
            self.delete(oldest_key)

    def delete(self, key: str) -> None:
        """Delete key from cache"""
        if key in self.cache:
            del self.cache[key]
        if key in self.expiry:
            del self.expiry[key]

    def clear(self) -> None:
        """Clear all cache"""
        self.cache.clear()
        self.expiry.clear()

    def size(self) -> int:
        """Return current cache size"""
        return len(self.cache)


class CircuitBreaker:
    """
    Circuit breaker for Redis failures
    Prevents cascading failures by failing fast
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: int = 30,
        expected_exception: type = RedisError
    ):
        """
        Initialize circuit breaker

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds before trying to close circuit
            expected_exception: Exception type to catch
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "closed"  # closed, open, half_open

    def call(self, func, *args, **kwargs):
        """
        Call function with circuit breaker protection

        Returns:
            Result of function or None if circuit is open
        """
        # Check if circuit should transition to half_open
        if self.state == "open":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "half_open"
                logger.info("Circuit breaker: Transitioning to half_open")
            else:
                # Circuit still open, fail fast
                return None

        try:
            result = func(*args, **kwargs)

            # Success - reset or close circuit
            if self.state == "half_open":
                self.state = "closed"
                self.failure_count = 0
                logger.info("Circuit breaker: Closed after successful call")

            return result

        except self.expected_exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                logger.error(f"Circuit breaker: Opened after {self.failure_count} failures")

            logger.warning(f"Circuit breaker: Caught exception ({self.failure_count}/{self.failure_threshold}): {e}")
            return None

    def is_open(self) -> bool:
        """Check if circuit is open"""
        return self.state == "open"


class TwoTierCache:
    """
    Two-tier cache with L1 (local) and L2 (Redis)
    L1: In-memory LRU cache (99% hit rate target)
    L2: Redis cache (distributed)
    L3: Fallback to PostgreSQL (via circuit breaker)

    Design approved by expert panel.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        l1_max_size: int = 1000,
        l1_ttl_seconds: int = 300,  # 5 minutes
        l2_ttl_seconds: int = 900,  # 15 minutes
        redis_timeout: int = 1,  # 1 second
        circuit_breaker_failures: int = 3,
        circuit_breaker_timeout: int = 30
    ):
        """
        Initialize two-tier cache

        Args:
            redis_url: Redis connection URL
            l1_max_size: L1 cache max size
            l1_ttl_seconds: L1 TTL
            l2_ttl_seconds: L2 (Redis) TTL
            redis_timeout: Redis operation timeout
            circuit_breaker_failures: Failures before opening circuit
            circuit_breaker_timeout: Seconds before retry
        """
        # L1 Cache (local)
        self.l1 = LRUCache(max_size=l1_max_size, ttl_seconds=l1_ttl_seconds)
        self.l2_ttl = l2_ttl_seconds

        # L2 Cache (Redis)
        try:
            self.redis = redis.from_url(
                redis_url,
                socket_timeout=redis_timeout,
                socket_connect_timeout=redis_timeout,
                decode_responses=True
            )
            # Test connection
            self.redis.ping()
            logger.info(f"✅ Redis connected: {redis_url}")
        except (ConnectionError, TimeoutError) as e:
            logger.error(f"❌ Redis connection failed: {e}")
            self.redis = None

        # Circuit breaker for Redis
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=circuit_breaker_failures,
            recovery_timeout=circuit_breaker_timeout,
            expected_exception=RedisError
        )

        # Metrics
        self.metrics = {
            "l1_hits": 0,
            "l1_misses": 0,
            "l2_hits": 0,
            "l2_misses": 0,
            "redis_errors": 0,
            "circuit_breaker_opens": 0
        }

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache (L1 → L2 → L3)

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        # Try L1 cache (local)
        value = self.l1.get(key)
        if value is not None:
            self.metrics["l1_hits"] += 1
            return value

        self.metrics["l1_misses"] += 1

        # Try L2 cache (Redis)
        if self.redis is not None:
            value = self._get_from_redis(key)
            if value is not None:
                self.metrics["l2_hits"] += 1
                # Populate L1 cache
                self.l1.set(key, value)
                return value

        self.metrics["l2_misses"] += 1
        return None

    def set(self, key: str, value: Any) -> bool:
        """
        Set value in cache (L1 + L2)

        Args:
            key: Cache key
            value: Value to cache

        Returns:
            True if successful
        """
        # Set in L1
        self.l1.set(key, value)

        # Set in L2 (Redis)
        if self.redis is not None:
            self._set_in_redis(key, value, ttl=self.l2_ttl)

        return True

    def delete(self, key: str) -> bool:
        """
        Delete key from cache (L1 + L2)

        Args:
            key: Cache key

        Returns:
            True if successful
        """
        # Delete from L1
        self.l1.delete(key)

        # Delete from L2 (Redis)
        if self.redis is not None:
            self._delete_from_redis(key)

        return True

    def invalidate(self, pattern: str) -> int:
        """
        Invalidate keys matching pattern

        Args:
            pattern: Key pattern (e.g., "api_key:*")

        Returns:
            Number of keys invalidated
        """
        count = 0

        # Clear L1 entirely (no pattern matching in OrderedDict)
        self.l1.clear()
        count += 1

        # Delete from L2 by pattern
        if self.redis is not None:
            count += self._delete_pattern_from_redis(pattern)

        logger.info(f"Invalidated cache pattern '{pattern}': {count} keys")
        return count

    def _get_from_redis(self, key: str) -> Optional[Any]:
        """Get value from Redis with circuit breaker"""
        if self.circuit_breaker.is_open():
            return None

        def redis_get():
            return self.redis.get(key)

        value = self.circuit_breaker.call(redis_get)

        if value is None and self.circuit_breaker.is_open():
            self.metrics["redis_errors"] += 1
            self.metrics["circuit_breaker_opens"] += 1

        return value

    def _set_in_redis(self, key: str, value: Any, ttl: int) -> bool:
        """Set value in Redis with circuit breaker"""
        if self.circuit_breaker.is_open():
            return False

        def redis_set():
            return self.redis.setex(key, ttl, value)

        result = self.circuit_breaker.call(redis_set)
        return result is not None

    def _delete_from_redis(self, key: str) -> bool:
        """Delete key from Redis with circuit breaker"""
        if self.circuit_breaker.is_open():
            return False

        def redis_del():
            return self.redis.delete(key)

        result = self.circuit_breaker.call(redis_del)
        return result is not None

    def _delete_pattern_from_redis(self, pattern: str) -> int:
        """Delete keys matching pattern from Redis"""
        if self.circuit_breaker.is_open():
            return 0

        def redis_delete_pattern():
            keys = self.redis.keys(pattern)
            if keys:
                return self.redis.delete(*keys)
            return 0

        result = self.circuit_breaker.call(redis_delete_pattern)
        return result if result is not None else 0

    def get_stats(self) -> Dict:
        """
        Get cache statistics

        Returns:
            Dictionary with cache metrics
        """
        total_requests = self.metrics["l1_hits"] + self.metrics["l1_misses"]
        l1_hit_rate = (self.metrics["l1_hits"] / total_requests * 100) if total_requests > 0 else 0

        l2_requests = self.metrics["l1_misses"]
        l2_hit_rate = (self.metrics["l2_hits"] / l2_requests * 100) if l2_requests > 0 else 0

        return {
            "l1": {
                "size": self.l1.size(),
                "max_size": self.l1.max_size,
                "hits": self.metrics["l1_hits"],
                "misses": self.metrics["l1_misses"],
                "hit_rate": round(l1_hit_rate, 2)
            },
            "l2": {
                "hits": self.metrics["l2_hits"],
                "misses": self.metrics["l2_misses"],
                "hit_rate": round(l2_hit_rate, 2)
            },
            "redis": {
                "connected": self.redis is not None and not self.circuit_breaker.is_open(),
                "errors": self.metrics["redis_errors"],
                "circuit_breaker_state": self.circuit_breaker.state,
                "circuit_breaker_opens": self.metrics["circuit_breaker_opens"]
            },
            "total_requests": total_requests
        }

    def health_check(self) -> Dict:
        """
        Check cache health

        Returns:
            Health status
        """
        healthy = True
        issues = []

        # Check L1
        if self.l1.size() == 0 and self.metrics["l1_hits"] == 0:
            issues.append("L1 cache empty (may be cold start)")

        # Check L2 (Redis)
        if self.redis is None:
            healthy = False
            issues.append("Redis not connected")
        elif self.circuit_breaker.is_open():
            healthy = False
            issues.append("Circuit breaker open (Redis failures)")

        # Check hit rates
        stats = self.get_stats()
        if stats["total_requests"] > 100:  # Only check if we have enough data
            if stats["l1"]["hit_rate"] < 95:
                issues.append(f"L1 hit rate low: {stats['l1']['hit_rate']}% (target: >95%)")

        return {
            "healthy": healthy,
            "redis_connected": self.redis is not None,
            "circuit_breaker_state": self.circuit_breaker.state,
            "issues": issues,
            "stats": stats
        }

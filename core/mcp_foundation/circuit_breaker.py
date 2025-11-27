"""
MCP Circuit Breaker - Protect against cascading failures

Provides:
- Circuit breaker pattern for MCP calls
- Automatic failure detection
- Fallback to cached responses
- Auto-recovery with half-open state
"""

import logging
import time
from typing import Any, Callable, Optional, Dict
from enum import Enum
from dataclasses import dataclass
import functools

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Blocking calls due to failures
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""
    failure_threshold: int = 5  # Open circuit after N failures
    success_threshold: int = 2  # Close circuit after N successes (in half-open)
    timeout: float = 60.0  # Seconds to wait before trying half-open
    excluded_exceptions: tuple = ()  # Exceptions that don't count as failures


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker"""
    state: CircuitState
    failure_count: int
    success_count: int
    last_failure_time: Optional[float]
    last_success_time: Optional[float]
    total_calls: int
    total_failures: int
    total_successes: int
    opened_at: Optional[float]


class MCPCircuitBreaker:
    """
    Circuit Breaker for MCP calls

    Protects against:
    - Cascading failures
    - Repeated calls to failing services
    - Resource exhaustion

    States:
    - CLOSED: Normal operation, calls pass through
    - OPEN: Failures detected, calls blocked
    - HALF_OPEN: Testing recovery, limited calls allowed
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        """
        Initialize circuit breaker

        Args:
            name: Circuit breaker name (usually MCP name)
            config: Configuration options
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._last_success_time: Optional[float] = None
        self._opened_at: Optional[float] = None

        # Statistics
        self._total_calls = 0
        self._total_failures = 0
        self._total_successes = 0

        # Cache for fallback
        self._last_successful_response: Optional[Any] = None

        logger.debug(f"Initialized circuit breaker for {name}")

    @property
    def state(self) -> CircuitState:
        """Get current state"""
        return self._state

    def call(
        self,
        func: Callable,
        *args,
        fallback: Optional[Callable] = None,
        **kwargs
    ) -> Any:
        """
        Execute function with circuit breaker protection

        Args:
            func: Function to call
            *args: Function arguments
            fallback: Optional fallback function if circuit is open
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerError: If circuit is open and no fallback
        """
        self._total_calls += 1

        # Check if circuit is open
        if self._state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                logger.info(f"Circuit breaker {self.name}: OPEN → HALF_OPEN")
            else:
                logger.warning(
                    f"Circuit breaker {self.name} is OPEN, blocking call"
                )
                if fallback:
                    return fallback(*args, **kwargs)
                elif self._last_successful_response is not None:
                    logger.info("Returning cached response")
                    return self._last_successful_response
                else:
                    raise CircuitBreakerError(
                        f"Circuit breaker {self.name} is OPEN"
                    )

        # Attempt the call
        try:
            result = func(*args, **kwargs)
            self._on_success(result)
            return result

        except Exception as e:
            # Check if exception should be ignored
            if isinstance(e, self.config.excluded_exceptions):
                logger.debug(f"Exception {type(e).__name__} excluded from circuit breaker")
                raise

            self._on_failure(e)
            raise

    def _on_success(self, result: Any) -> None:
        """Handle successful call"""
        self._success_count += 1
        self._total_successes += 1
        self._last_success_time = time.time()
        self._last_successful_response = result

        if self._state == CircuitState.HALF_OPEN:
            if self._success_count >= self.config.success_threshold:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._opened_at = None
                logger.info(
                    f"Circuit breaker {self.name}: HALF_OPEN → CLOSED "
                    f"(after {self._success_count} successes)"
                )

    def _on_failure(self, exception: Exception) -> None:
        """Handle failed call"""
        self._failure_count += 1
        self._total_failures += 1
        self._last_failure_time = time.time()

        logger.warning(
            f"Circuit breaker {self.name}: call failed "
            f"({self._failure_count}/{self.config.failure_threshold}): {exception}"
        )

        if self._state == CircuitState.HALF_OPEN:
            # Immediate open on failure in half-open
            self._state = CircuitState.OPEN
            self._opened_at = time.time()
            logger.error(
                f"Circuit breaker {self.name}: HALF_OPEN → OPEN "
                f"(failure during recovery test)"
            )

        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self.config.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.time()
                logger.error(
                    f"Circuit breaker {self.name}: CLOSED → OPEN "
                    f"(reached {self._failure_count} failures)"
                )

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if self._opened_at is None:
            return False

        time_open = time.time() - self._opened_at
        return time_open >= self.config.timeout

    def reset(self) -> None:
        """Manually reset circuit breaker"""
        old_state = self._state
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._opened_at = None

        logger.info(f"Circuit breaker {self.name}: manually reset from {old_state}")

    def get_stats(self) -> CircuitBreakerStats:
        """Get circuit breaker statistics"""
        return CircuitBreakerStats(
            state=self._state,
            failure_count=self._failure_count,
            success_count=self._success_count,
            last_failure_time=self._last_failure_time,
            last_success_time=self._last_success_time,
            total_calls=self._total_calls,
            total_failures=self._total_failures,
            total_successes=self._total_successes,
            opened_at=self._opened_at,
        )


class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open"""
    pass


class CircuitBreakerManager:
    """
    Manager for multiple circuit breakers

    Provides:
    - Central management of all MCP circuit breakers
    - Health monitoring
    - Batch operations
    """

    def __init__(self):
        self._breakers: Dict[str, MCPCircuitBreaker] = {}

    def get_breaker(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None
    ) -> MCPCircuitBreaker:
        """
        Get or create circuit breaker

        Args:
            name: Breaker name
            config: Optional configuration

        Returns:
            MCPCircuitBreaker instance
        """
        if name not in self._breakers:
            self._breakers[name] = MCPCircuitBreaker(name, config)

        return self._breakers[name]

    def get_all_stats(self) -> Dict[str, CircuitBreakerStats]:
        """Get stats for all circuit breakers"""
        return {
            name: breaker.get_stats()
            for name, breaker in self._breakers.items()
        }

    def get_open_circuits(self) -> list[str]:
        """Get names of all open circuits"""
        return [
            name
            for name, breaker in self._breakers.items()
            if breaker.state == CircuitState.OPEN
        ]

    def reset_all(self) -> None:
        """Reset all circuit breakers"""
        for breaker in self._breakers.values():
            breaker.reset()

        logger.info(f"Reset all {len(self._breakers)} circuit breakers")

    def health_check(self) -> Dict[str, Any]:
        """
        Check health of all circuits

        Returns:
            Health status summary
        """
        stats = self.get_all_stats()

        total = len(stats)
        closed = sum(1 for s in stats.values() if s.state == CircuitState.CLOSED)
        half_open = sum(1 for s in stats.values() if s.state == CircuitState.HALF_OPEN)
        open_circuits = sum(1 for s in stats.values() if s.state == CircuitState.OPEN)

        total_calls = sum(s.total_calls for s in stats.values())
        total_failures = sum(s.total_failures for s in stats.values())

        failure_rate = (total_failures / total_calls * 100) if total_calls > 0 else 0

        return {
            "total_breakers": total,
            "closed": closed,
            "half_open": half_open,
            "open": open_circuits,
            "total_calls": total_calls,
            "total_failures": total_failures,
            "failure_rate_percent": round(failure_rate, 2),
            "open_circuit_names": self.get_open_circuits(),
        }


# Decorator for easy circuit breaker usage
def circuit_breaker(
    name: str,
    fallback: Optional[Callable] = None,
    config: Optional[CircuitBreakerConfig] = None
):
    """
    Decorator to add circuit breaker to a function

    Args:
        name: Circuit breaker name
        fallback: Optional fallback function
        config: Optional circuit breaker config

    Example:
        @circuit_breaker("my_mcp", fallback=lambda: "default")
        def call_mcp():
            return external_service.call()
    """
    def decorator(func):
        manager = CircuitBreakerManager()
        breaker = manager.get_breaker(name, config)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return breaker.call(func, *args, fallback=fallback, **kwargs)

        return wrapper
    return decorator


# Global circuit breaker manager
_global_manager = None


def get_circuit_breaker_manager() -> CircuitBreakerManager:
    """Get the global circuit breaker manager"""
    global _global_manager
    if _global_manager is None:
        _global_manager = CircuitBreakerManager()
    return _global_manager

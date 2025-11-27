"""
Circuit breaker pattern for fault tolerance
Implements resilience patterns recommended by all LLMs
"""

import asyncio
from enum import Enum
from typing import Callable, Any, Optional, Dict
from datetime import datetime, timedelta
import logging
from functools import wraps
import random

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Circuit tripped, failing fast
    HALF_OPEN = "half_open"  # Testing if service recovered

class CircuitBreaker:
    """
    Circuit breaker implementation with:
    - Automatic state transitions
    - Configurable thresholds
    - Exponential backoff
    - Success rate tracking
    """
    
    def __init__(self,
                 failure_threshold: int = 5,
                 recovery_timeout: int = 60,
                 expected_exception: type = Exception,
                 success_threshold: int = 2):
        
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.success_threshold = success_threshold
        
        # State management
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.last_success_time: Optional[datetime] = None
        
        # Statistics
        self.stats = {
            'total_calls': 0,
            'successful_calls': 0,
            'failed_calls': 0,
            'rejected_calls': 0,
            'state_transitions': []
        }
    
    def _should_attempt_reset(self) -> bool:
        """Check if circuit should attempt reset"""
        if self.state != CircuitState.OPEN:
            return False
        
        if not self.last_failure_time:
            return False
        
        time_since_failure = datetime.now() - self.last_failure_time
        return time_since_failure > timedelta(seconds=self.recovery_timeout)
    
    def _record_success(self):
        """Record successful call"""
        self.success_count += 1
        self.last_success_time = datetime.now()
        self.stats['successful_calls'] += 1
        
        if self.state == CircuitState.HALF_OPEN:
            if self.success_count >= self.success_threshold:
                self._transition_to(CircuitState.CLOSED)
                self.failure_count = 0
                self.success_count = 0
    
    def _record_failure(self):
        """Record failed call"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        self.stats['failed_calls'] += 1
        
        if self.state == CircuitState.HALF_OPEN:
            self._transition_to(CircuitState.OPEN)
        elif self.state == CircuitState.CLOSED:
            if self.failure_count >= self.failure_threshold:
                self._transition_to(CircuitState.OPEN)
    
    def _transition_to(self, new_state: CircuitState):
        """Transition to new state"""
        old_state = self.state
        self.state = new_state
        
        self.stats['state_transitions'].append({
            'from': old_state.value,
            'to': new_state.value,
            'timestamp': datetime.now().isoformat()
        })
        
        logger.info(f"Circuit breaker state transition: {old_state.value} -> {new_state.value}")
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection"""
        self.stats['total_calls'] += 1
        
        # Check if we should attempt reset
        if self._should_attempt_reset():
            self._transition_to(CircuitState.HALF_OPEN)
            self.success_count = 0
        
        # Fail fast if circuit is open
        if self.state == CircuitState.OPEN:
            self.stats['rejected_calls'] += 1
            raise Exception(f"Circuit breaker is OPEN. Service unavailable.")
        
        try:
            # Execute the function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            self._record_success()
            return result
            
        except self.expected_exception as e:
            self._record_failure()
            raise e
    
    def get_state(self) -> str:
        """Get current circuit state"""
        return self.state.value
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics"""
        return {
            'state': self.state.value,
            'failure_count': self.failure_count,
            'success_count': self.success_count,
            **self.stats
        }
    
    def reset(self):
        """Manually reset circuit breaker"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        logger.info("Circuit breaker manually reset")

class RetryPolicy:
    """
    Retry policy with exponential backoff
    """
    
    def __init__(self,
                 max_attempts: int = 3,
                 base_delay: float = 1.0,
                 max_delay: float = 60.0,
                 exponential_base: float = 2.0,
                 jitter: bool = True):
        
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt"""
        delay = min(
            self.base_delay * (self.exponential_base ** attempt),
            self.max_delay
        )
        
        if self.jitter:
            # Add random jitter to prevent thundering herd
            delay = delay * (0.5 + random.random())
        
        return delay

def with_circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
    expected_exception: type = Exception
):
    """Decorator to add circuit breaker to function"""
    def decorator(func):
        breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            expected_exception=expected_exception
        )
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await breaker.call(func, *args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(
                breaker.call(func, *args, **kwargs)
            )
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator

def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    exceptions: tuple = (Exception,)
):
    """Decorator to add retry logic to function"""
    def decorator(func):
        policy = RetryPolicy(
            max_attempts=max_attempts,
            base_delay=base_delay
        )
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_attempts - 1:
                        delay = policy.get_delay(attempt)
                        logger.debug(f"Retry {attempt + 1}/{max_attempts} after {delay:.2f}s")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"All {max_attempts} attempts failed")
            
            raise last_exception
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_attempts - 1:
                        delay = policy.get_delay(attempt)
                        logger.debug(f"Retry {attempt + 1}/{max_attempts} after {delay:.2f}s")
                        import time
                        time.sleep(delay)
                    else:
                        logger.error(f"All {max_attempts} attempts failed")
            
            raise last_exception
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator

class CircuitBreakerManager:
    """
    Manages multiple circuit breakers for different services
    """
    
    def __init__(self):
        self.breakers: Dict[str, CircuitBreaker] = {}
    
    def get_or_create(self,
                      service: str,
                      failure_threshold: int = 5,
                      recovery_timeout: int = 60) -> CircuitBreaker:
        """Get existing or create new circuit breaker for service"""
        if service not in self.breakers:
            self.breakers[service] = CircuitBreaker(
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout
            )
        
        return self.breakers[service]
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all circuit breakers"""
        return {
            service: breaker.get_stats()
            for service, breaker in self.breakers.items()
        }
    
    def reset_all(self):
        """Reset all circuit breakers"""
        for breaker in self.breakers.values():
            breaker.reset()

# Global circuit breaker manager
global_breaker_manager = CircuitBreakerManager()

def get_circuit_breaker(service: str) -> CircuitBreaker:
    """Get circuit breaker for specific service"""
    return global_breaker_manager.get_or_create(service)

def get_all_circuit_stats() -> Dict[str, Any]:
    """Get statistics for all circuit breakers"""
    return global_breaker_manager.get_all_stats()
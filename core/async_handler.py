#!/usr/bin/env python3
"""
Async Handler - Elimina todo I/O bloqueante del sistema
Implementa timeouts y circuit breakers en todas las operaciones
"""

import asyncio
import functools
import time
from typing import Any, Callable, Optional, TypeVar, Union
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')

class CircuitBreaker:
    """Circuit breaker pattern para prevenir cascadas de fallos"""
    
    def __init__(self, failure_threshold: int = 5, timeout: float = 60.0, recovery_time: float = 30.0):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.recovery_time = recovery_time
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open
        
    def call(self, func: Callable) -> Callable:
        """Decorator para aplicar circuit breaker"""
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Check if circuit is open
            if self.state == "open":
                if self.last_failure_time:
                    time_since_failure = time.time() - self.last_failure_time
                    if time_since_failure > self.recovery_time:
                        self.state = "half-open"
                    else:
                        raise Exception(f"Circuit breaker is open. Wait {self.recovery_time - time_since_failure:.1f}s")
            
            try:
                # Apply timeout
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=self.timeout)
                
                # Success - reset failures
                if self.state == "half-open":
                    self.state = "closed"
                self.failure_count = 0
                
                return result
                
            except asyncio.TimeoutError:
                self.failure_count += 1
                self.last_failure_time = time.time()
                
                if self.failure_count >= self.failure_threshold:
                    self.state = "open"
                    logger.error(f"Circuit breaker opened after {self.failure_count} failures")
                
                raise TimeoutError(f"Operation timed out after {self.timeout}s")
                
            except Exception as e:
                self.failure_count += 1
                self.last_failure_time = time.time()
                
                if self.failure_count >= self.failure_threshold:
                    self.state = "open"
                
                raise e
        
        return wrapper


class AsyncHandler:
    """Main async handler for all I/O operations"""
    
    def __init__(self, default_timeout: float = 5.0):
        self.default_timeout = default_timeout
        self.circuit_breakers = {}
        
    def get_circuit_breaker(self, name: str) -> CircuitBreaker:
        """Get or create a circuit breaker for a service"""
        if name not in self.circuit_breakers:
            self.circuit_breakers[name] = CircuitBreaker(timeout=self.default_timeout)
        return self.circuit_breakers[name]
    
    async def safe_execute(
        self, 
        func: Callable[..., T], 
        *args,
        timeout: Optional[float] = None,
        fallback: Optional[T] = None,
        service_name: str = "default",
        **kwargs
    ) -> Optional[T]:
        """
        Safely execute any function with timeout and fallback
        
        Args:
            func: Function to execute
            timeout: Custom timeout (uses default if None)
            fallback: Value to return on failure
            service_name: Name for circuit breaker tracking
        """
        timeout = timeout or self.default_timeout
        
        try:
            # If it's already async
            if asyncio.iscoroutinefunction(func):
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
            else:
                # Run sync function in executor to avoid blocking
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, func, *args),
                    timeout=timeout
                )
            
            return result
            
        except asyncio.TimeoutError:
            logger.warning(f"{service_name}: Timeout after {timeout}s for {func.__name__}")
            return fallback
            
        except Exception as e:
            logger.error(f"{service_name}: Error in {func.__name__}: {e}")
            return fallback
    
    async def parallel_execute(
        self,
        tasks: list[tuple[Callable, tuple, dict]],
        max_concurrent: int = 10
    ) -> list[Any]:
        """
        Execute multiple tasks in parallel with concurrency limit
        
        Args:
            tasks: List of (function, args, kwargs) tuples
            max_concurrent: Maximum concurrent tasks
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def run_with_semaphore(func, args, kwargs):
            async with semaphore:
                return await self.safe_execute(func, *args, **kwargs)
        
        results = await asyncio.gather(
            *[run_with_semaphore(func, args, kwargs) for func, args, kwargs in tasks],
            return_exceptions=True
        )
        
        return results
    
    async def retry_with_backoff(
        self,
        func: Callable[..., T],
        *args,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        backoff_factor: float = 2.0,
        **kwargs
    ) -> Optional[T]:
        """
        Retry a function with exponential backoff
        """
        delay = initial_delay
        
        for attempt in range(max_retries):
            try:
                result = await self.safe_execute(func, *args, **kwargs)
                if result is not None:
                    return result
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                
                logger.info(f"Retry {attempt + 1}/{max_retries} after {delay}s")
                await asyncio.sleep(delay)
                delay *= backoff_factor
        
        return None


# Global instance
async_handler = AsyncHandler()

# Convenience decorators
def async_timeout(seconds: float = 5.0):
    """Decorator to add timeout to any async function"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
        return wrapper
    return decorator


def make_async(func: Callable) -> Callable:
    """Convert a sync function to async"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, *args, **kwargs)
    return wrapper


# Example usage
async def example_usage():
    """Example of how to use the async handler"""
    
    # Safe execution with timeout
    result = await async_handler.safe_execute(
        some_slow_function,
        timeout=3.0,
        fallback="default_value"
    )
    
    # Parallel execution
    tasks = [
        (fetch_from_api1, (), {}),
        (fetch_from_api2, (), {}),
        (fetch_from_api3, (), {})
    ]
    results = await async_handler.parallel_execute(tasks, max_concurrent=2)
    
    # Retry with backoff
    data = await async_handler.retry_with_backoff(
        unreliable_api_call,
        max_retries=3,
        initial_delay=1.0
    )
    
    return results


def some_slow_function():
    """Example slow function"""
    time.sleep(10)
    return "done"


async def fetch_from_api1():
    """Example API call"""
    await asyncio.sleep(1)
    return "api1_data"


async def fetch_from_api2():
    """Example API call"""
    await asyncio.sleep(1)
    return "api2_data"


async def fetch_from_api3():
    """Example API call"""
    await asyncio.sleep(1)
    return "api3_data"


async def unreliable_api_call():
    """Example unreliable API"""
    import random
    if random.random() > 0.5:
        raise Exception("Random failure")
    return "success"


if __name__ == "__main__":
    # Test the async handler
    asyncio.run(example_usage())
"""
Circuit Breaker Pattern for API Resilience
Automatically handles failures and switches to fallback APIs
"""

import time
import asyncio
import threading
from typing import Dict, Any, Optional, Callable, List
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from collections import deque

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing if service recovered

@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""
    failure_threshold: int = 5          # Failures before opening
    success_threshold: int = 2          # Successes to close from half-open
    timeout: int = 60                    # Seconds before trying half-open
    half_open_max_calls: int = 3        # Max calls in half-open state
    
class CircuitBreaker:
    """
    Circuit breaker implementation for individual APIs
    """
    
    def __init__(self, 
                 name: str,
                 config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.half_open_calls = 0
        
        # Statistics
        self.call_stats = deque(maxlen=100)  # Last 100 calls
        self.state_changes = []
        self.total_calls = 0
        self.total_failures = 0
        self.total_successes = 0
        
        self.lock = threading.Lock()
        
    def _change_state(self, new_state: CircuitState):
        """Change circuit state and log it"""
        if self.state != new_state:
            old_state = self.state
            self.state = new_state
            self.state_changes.append({
                "timestamp": datetime.now().isoformat(),
                "from": old_state.value,
                "to": new_state.value
            })
            logger.info(f"Circuit {self.name}: {old_state.value} -> {new_state.value}")
            
            # Reset counters on state change
            if new_state == CircuitState.CLOSED:
                self.failure_count = 0
                self.success_count = 0
            elif new_state == CircuitState.HALF_OPEN:
                self.half_open_calls = 0
    
    def is_available(self) -> bool:
        """Check if circuit allows calls"""
        with self.lock:
            if self.state == CircuitState.CLOSED:
                return True
            
            if self.state == CircuitState.OPEN:
                # Check if timeout has passed
                if self.last_failure_time:
                    time_since_failure = time.time() - self.last_failure_time
                    if time_since_failure >= self.config.timeout:
                        self._change_state(CircuitState.HALF_OPEN)
                        return True
                return False
            
            if self.state == CircuitState.HALF_OPEN:
                # Allow limited calls in half-open state
                return self.half_open_calls < self.config.half_open_max_calls
            
            return False
    
    def record_success(self):
        """Record a successful call"""
        with self.lock:
            self.total_calls += 1
            self.total_successes += 1
            self.call_stats.append({"time": time.time(), "success": True})
            
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    self._change_state(CircuitState.CLOSED)
            elif self.state == CircuitState.CLOSED:
                # Reset failure count on success in closed state
                self.failure_count = 0
    
    def record_failure(self, error: Exception = None):
        """Record a failed call"""
        with self.lock:
            self.total_calls += 1
            self.total_failures += 1
            self.last_failure_time = time.time()
            self.call_stats.append({"time": time.time(), "success": False, "error": str(error)})
            
            if self.state == CircuitState.CLOSED:
                self.failure_count += 1
                if self.failure_count >= self.config.failure_threshold:
                    self._change_state(CircuitState.OPEN)
            elif self.state == CircuitState.HALF_OPEN:
                # Single failure in half-open reopens the circuit
                self._change_state(CircuitState.OPEN)
    
    def call(self, func: Callable, *args, **kwargs):
        """Execute a function through the circuit breaker"""
        if not self.is_available():
            raise Exception(f"Circuit breaker {self.name} is OPEN")
        
        if self.state == CircuitState.HALF_OPEN:
            with self.lock:
                self.half_open_calls += 1
        
        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure(e)
            raise
    
    async def async_call(self, func: Callable, *args, **kwargs):
        """Execute an async function through the circuit breaker"""
        if not self.is_available():
            raise Exception(f"Circuit breaker {self.name} is OPEN")
        
        if self.state == CircuitState.HALF_OPEN:
            with self.lock:
                self.half_open_calls += 1
        
        try:
            result = await func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure(e)
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics"""
        success_rate = (self.total_successes / self.total_calls * 100) if self.total_calls > 0 else 0
        
        return {
            "name": self.name,
            "state": self.state.value,
            "total_calls": self.total_calls,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "success_rate": f"{success_rate:.1f}%",
            "failure_count": self.failure_count,
            "state_changes": len(self.state_changes),
            "last_state_change": self.state_changes[-1] if self.state_changes else None
        }
    
    def reset(self):
        """Reset the circuit breaker"""
        with self.lock:
            self._change_state(CircuitState.CLOSED)
            self.failure_count = 0
            self.success_count = 0
            self.half_open_calls = 0
            self.last_failure_time = None


class ResilientAPIManager:
    """
    Manages multiple APIs with circuit breakers and automatic fallback
    """
    
    def __init__(self, 
                 fallback_chain: List[str] = None,
                 circuit_config: CircuitBreakerConfig = None):
        
        self.fallback_chain = fallback_chain or ["gemini", "claude", "openai"]
        self.circuit_config = circuit_config or CircuitBreakerConfig()
        
        # Create circuit breakers for each API
        self.circuit_breakers = {
            api: CircuitBreaker(api, self.circuit_config)
            for api in self.fallback_chain
        }
        
        # Track which API is currently primary
        self.current_primary = self.fallback_chain[0]
        
        # Statistics
        self.total_requests = 0
        self.fallback_count = 0
        self.complete_failures = 0
        
    def _get_available_apis(self) -> List[str]:
        """Get list of currently available APIs"""
        available = []
        for api in self.fallback_chain:
            if self.circuit_breakers[api].is_available():
                available.append(api)
        return available
    
    def select_api(self, preferred: str = None) -> Optional[str]:
        """Select an available API, preferring the specified one"""
        available = self._get_available_apis()
        
        if not available:
            return None
        
        # If preferred API is available, use it
        if preferred and preferred in available:
            return preferred
        
        # Otherwise use first available in fallback chain
        for api in self.fallback_chain:
            if api in available:
                return api
        
        return available[0] if available else None
    
    async def call_with_fallback(self, 
                                api_functions: Dict[str, Callable],
                                *args,
                                preferred_api: str = None,
                                **kwargs) -> Dict[str, Any]:
        """
        Call APIs with automatic fallback on failure
        
        Args:
            api_functions: Dict mapping API names to their callable functions
            preferred_api: Preferred API to try first
            *args, **kwargs: Arguments to pass to the API functions
            
        Returns:
            Dict with response and metadata
        """
        self.total_requests += 1
        errors = []
        apis_tried = []
        
        # Determine order to try APIs
        if preferred_api and preferred_api in self.fallback_chain:
            # Put preferred API first
            api_order = [preferred_api] + [api for api in self.fallback_chain if api != preferred_api]
        else:
            api_order = self.fallback_chain
        
        for api in api_order:
            if api not in api_functions:
                continue
                
            circuit = self.circuit_breakers[api]
            
            if not circuit.is_available():
                logger.debug(f"Skipping {api} - circuit is {circuit.state.value}")
                continue
            
            apis_tried.append(api)
            
            try:
                # Try to call the API
                start_time = time.time()
                
                if asyncio.iscoroutinefunction(api_functions[api]):
                    result = await circuit.async_call(api_functions[api], *args, **kwargs)
                else:
                    result = circuit.call(api_functions[api], *args, **kwargs)
                
                latency = time.time() - start_time
                
                # Success!
                if api != self.fallback_chain[0]:
                    self.fallback_count += 1
                
                return {
                    "success": True,
                    "api_used": api,
                    "response": result,
                    "latency": latency,
                    "apis_tried": apis_tried,
                    "fallback_used": api != self.fallback_chain[0]
                }
                
            except Exception as e:
                errors.append({
                    "api": api,
                    "error": str(e)
                })
                logger.warning(f"API {api} failed: {e}")
                continue
        
        # All APIs failed
        self.complete_failures += 1
        
        return {
            "success": False,
            "api_used": None,
            "response": None,
            "errors": errors,
            "apis_tried": apis_tried,
            "message": "All APIs failed or unavailable"
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status of all managed APIs"""
        api_status = {}
        for api, circuit in self.circuit_breakers.items():
            stats = circuit.get_stats()
            api_status[api] = {
                "state": stats["state"],
                "success_rate": stats["success_rate"],
                "total_calls": stats["total_calls"]
            }
        
        available_apis = self._get_available_apis()
        
        return {
            "healthy_apis": len(available_apis),
            "total_apis": len(self.circuit_breakers),
            "apis": api_status,
            "available": available_apis,
            "primary": self.current_primary,
            "stats": {
                "total_requests": self.total_requests,
                "fallback_used": self.fallback_count,
                "complete_failures": self.complete_failures,
                "success_rate": f"{((self.total_requests - self.complete_failures) / self.total_requests * 100):.1f}%" if self.total_requests > 0 else "N/A"
            }
        }
    
    def reset_circuit(self, api: str):
        """Manually reset a circuit breaker"""
        if api in self.circuit_breakers:
            self.circuit_breakers[api].reset()
            logger.info(f"Circuit breaker for {api} has been reset")
    
    def reset_all_circuits(self):
        """Reset all circuit breakers"""
        for circuit in self.circuit_breakers.values():
            circuit.reset()
        logger.info("All circuit breakers have been reset")


# Example implementation for testing
async def test_resilient_api():
    """Test the resilient API manager"""
    
    # Simulate API functions
    async def call_openai(prompt):
        # Simulate intermittent failures
        import random
        if random.random() < 0.3:  # 30% failure rate
            raise Exception("OpenAI API error")
        return {"response": "OpenAI response", "model": "gpt-4"}
    
    async def call_claude(prompt):
        # Simulate occasional failures
        import random
        if random.random() < 0.1:  # 10% failure rate
            raise Exception("Claude API error")
        return {"response": "Claude response", "model": "claude-3"}
    
    async def call_gemini(prompt):
        # Most reliable
        import random
        if random.random() < 0.05:  # 5% failure rate
            raise Exception("Gemini API error")
        return {"response": "Gemini response", "model": "gemini-1.5"}
    
    # Create resilient manager
    manager = ResilientAPIManager(
        fallback_chain=["openai", "claude", "gemini"],
        circuit_config=CircuitBreakerConfig(
            failure_threshold=3,
            timeout=30
        )
    )
    
    # Test with multiple calls
    api_functions = {
        "openai": call_openai,
        "claude": call_claude,
        "gemini": call_gemini
    }
    
    results = []
    for i in range(20):
        result = await manager.call_with_fallback(
            api_functions,
            f"Test prompt {i}"
        )
        results.append(result)
        
        if result["success"]:
            print(f"Call {i+1}: ✅ Used {result['api_used']} (latency: {result['latency']:.3f}s)")
        else:
            print(f"Call {i+1}: ❌ All APIs failed")
    
    # Show health status
    health = manager.get_health_status()
    print(f"\nHealth Status:")
    print(f"  Available APIs: {health['available']}")
    print(f"  Success Rate: {health['stats']['success_rate']}")
    print(f"  Fallbacks Used: {health['stats']['fallback_used']}")
    
    return results


if __name__ == "__main__":
    # Run test
    print("Testing Resilient API Manager with Circuit Breakers\n" + "="*50)
    asyncio.run(test_resilient_api())
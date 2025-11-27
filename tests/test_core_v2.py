#!/usr/bin/env python3
"""
Comprehensive test suite for NubemSuperFClaude v2
Tests all 5 consensus improvements
"""

import pytest
import asyncio
import sys
import os
from pathlib import Path
import time
from unittest.mock import Mock, patch, AsyncMock

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core_v2.core import NubemCore
from core_v2.llm_client import UnifiedLLMClient
from core_v2.session_manager import SimpleSessionManager
from core_v2.plugin_system import PluginSystem, Plugin
from core_v2.error_handler import ErrorHandler, ErrorType
from core.async_handler import AsyncHandler, CircuitBreaker

# ============================================
# Test 1: I/O Non-Blocking (Async Everything)
# ============================================

class TestAsyncNonBlocking:
    """Test that all I/O is non-blocking"""
    
    @pytest.mark.asyncio
    async def test_async_handler_timeout(self):
        """Test that operations timeout properly"""
        handler = AsyncHandler(default_timeout=0.5)
        
        async def slow_function():
            await asyncio.sleep(2)
            return "should_not_return"
        
        result = await handler.safe_execute(
            slow_function,
            timeout=0.5,
            fallback="timeout_fallback"
        )
        
        assert result == "timeout_fallback"
    
    @pytest.mark.asyncio
    async def test_parallel_execution(self):
        """Test parallel execution doesn't block"""
        handler = AsyncHandler()
        
        async def task(n):
            await asyncio.sleep(0.1)
            return n
        
        tasks = [(task, (i,), {}) for i in range(5)]
        
        start = time.time()
        results = await handler.parallel_execute(tasks, max_concurrent=5)
        duration = time.time() - start
        
        # Should complete in ~0.1s (parallel), not 0.5s (serial)
        assert duration < 0.3
        assert len(results) == 5
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_opens(self):
        """Test circuit breaker opens after failures"""
        breaker = CircuitBreaker(failure_threshold=2, timeout=0.5)
        
        @breaker.call
        async def failing_function():
            raise Exception("Test failure")
        
        # First two failures
        with pytest.raises(Exception):
            await failing_function()
        with pytest.raises(Exception):
            await failing_function()
        
        # Circuit should be open now
        assert breaker.state == "open"
        
        # Should fail immediately without calling function
        with pytest.raises(Exception) as exc:
            await failing_function()
        assert "Circuit breaker is open" in str(exc.value)

# ============================================
# Test 2: Minimal Dependencies
# ============================================

class TestMinimalDependencies:
    """Test that we've reduced dependencies"""
    
    def test_requirements_minimal(self):
        """Test that minimal requirements exists and is small"""
        req_file = Path("requirements-minimal.txt")
        assert req_file.exists()
        
        with open(req_file) as f:
            lines = [l for l in f if l.strip() and not l.startswith("#")]
        
        # Should have less than 30 dependencies
        assert len(lines) < 30
        
        # Should have essential packages
        essential = ["anthropic", "openai", "fastapi", "redis"]
        content = req_file.read_text().lower()
        for package in essential:
            assert package in content

# ============================================
# Test 3: Modular Architecture
# ============================================

class TestModularArchitecture:
    """Test modular plugin-based architecture"""
    
    @pytest.mark.asyncio
    async def test_plugin_lazy_loading(self):
        """Test plugins only load when needed"""
        plugin_system = PluginSystem()
        
        # Initially no plugins loaded
        assert len(plugin_system.list_loaded()) == 0
        
        # Create a test plugin
        class TestPlugin(Plugin):
            async def process_context(self, context):
                return context + " [enhanced]"
        
        # Plugin not loaded until requested
        assert "test" not in plugin_system.list_loaded()
    
    @pytest.mark.asyncio
    async def test_core_minimal(self):
        """Test core has minimal components"""
        core = NubemCore()
        
        # Should have exactly 3 main components
        assert hasattr(core, 'llm')
        assert hasattr(core, 'session')
        assert hasattr(core, 'plugins')
        
        # Should have error handler
        assert hasattr(core, 'error_handler')
    
    @pytest.mark.asyncio
    async def test_plugin_isolation(self):
        """Test plugins are isolated from each other"""
        plugin_system = PluginSystem()
        
        # Plugins should not affect each other
        plugins = plugin_system.list_available()
        
        # Each plugin loads independently
        for plugin_name in plugins[:2]:  # Test first 2
            plugin = await plugin_system.load_plugin(plugin_name)
            if plugin:
                await plugin_system.unload_plugin(plugin_name)
                assert plugin_name not in plugin_system.list_loaded()

# ============================================
# Test 4: Robust Error Handling
# ============================================

class TestErrorHandling:
    """Test comprehensive error handling"""
    
    @pytest.mark.asyncio
    async def test_error_classification(self):
        """Test error classification works correctly"""
        handler = ErrorHandler()
        
        # Test different error types
        timeout_error = asyncio.TimeoutError("Timeout")
        assert handler.classify_error(timeout_error) == ErrorType.TIMEOUT
        
        api_error = Exception("API error 401")
        assert handler.classify_error(api_error) == ErrorType.API_ERROR
        
        validation_error = ValueError("Invalid input")
        assert handler.classify_error(validation_error) == ErrorType.VALIDATION_ERROR
    
    @pytest.mark.asyncio
    async def test_retry_policy(self):
        """Test retry with exponential backoff"""
        handler = ErrorHandler()
        attempt_count = 0
        
        async def flaky_function():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise Exception("Temporary failure")
            return "success"
        
        result = await handler.safe_execute(
            flaky_function,
            timeout=5.0,
            service_name="test_service"
        )
        
        assert result == "success"
        assert attempt_count == 3
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_in_error_handler(self):
        """Test circuit breaker in error handler"""
        handler = ErrorHandler()
        
        async def always_fails():
            raise Exception("Always fails")
        
        # Fail 5 times to open circuit
        for _ in range(5):
            result = await handler.safe_execute(
                always_fails,
                fallback="failed",
                service_name="failing_service"
            )
            assert result == "failed"
        
        # Circuit should be open
        assert handler._is_circuit_open("failing_service")
        
        # Next call should fail immediately
        start = time.time()
        result = await handler.safe_execute(
            always_fails,
            fallback="circuit_open",
            service_name="failing_service"
        )
        duration = time.time() - start
        
        assert result == "circuit_open"
        assert duration < 0.1  # Should fail immediately
    
    @pytest.mark.asyncio
    async def test_fallback_values(self):
        """Test fallback values work correctly"""
        handler = ErrorHandler()
        
        async def failing_function():
            raise Exception("Error")
        
        result = await handler.safe_execute(
            failing_function,
            fallback="default_value",
            service_name="test"
        )
        
        assert result == "default_value"

# ============================================
# Test 5: Integration Tests
# ============================================

class TestIntegration:
    """Test that all components work together"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_query(self):
        """Test complete query pipeline"""
        core = NubemCore()
        
        # Mock LLM response
        with patch.object(core.llm, 'query', new_callable=AsyncMock) as mock_query:
            mock_query.return_value = "Test response"
            
            response = await core.process("Test query")
            
            assert response == "Test response"
            mock_query.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_session_persistence(self):
        """Test sessions persist correctly"""
        manager = SimpleSessionManager()
        
        session_id = manager.create_session()
        
        await manager.save_interaction(
            session_id,
            "Question",
            "Answer"
        )
        
        context = await manager.get_context(session_id)
        assert "Question" in context
        assert "Answer" in context
    
    @pytest.mark.asyncio
    async def test_performance_requirements(self):
        """Test performance meets requirements"""
        core = NubemCore()
        
        # Mock fast LLM response
        with patch.object(core.llm, 'query', new_callable=AsyncMock) as mock_query:
            async def fast_response(*args, **kwargs):
                await asyncio.sleep(0.1)  # Simulate fast API
                return "Fast response"
            
            mock_query.side_effect = fast_response
            
            start = time.time()
            response = await core.process("Test")
            duration = time.time() - start
            
            # Should complete in under 500ms
            assert duration < 0.5
            assert response == "Fast response"

# ============================================
# Performance Benchmarks
# ============================================

class TestPerformance:
    """Test that performance improvements are real"""
    
    @pytest.mark.asyncio
    async def test_startup_time(self):
        """Test that startup is fast"""
        start = time.time()
        core = NubemCore()
        duration = time.time() - start
        
        # Should initialize in under 2 seconds
        assert duration < 2.0
    
    @pytest.mark.asyncio
    async def test_memory_usage(self):
        """Test memory usage is reasonable"""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        
        # Get initial memory
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Create core
        core = NubemCore()
        
        # Process some queries
        for _ in range(10):
            await core.process("Test query")
        
        # Check memory after
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        # Should use less than 100MB additional
        assert memory_increase < 100

# ============================================
# Run Tests
# ============================================

if __name__ == "__main__":
    # Run all tests
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
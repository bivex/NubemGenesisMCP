"""
Unified Test Suite for NubemSuperFClaude
Comprehensive testing for all major components
"""

import pytest
import asyncio
import json
import os
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
import tempfile
from pathlib import Path

# Import components to test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.unified_llm_adapter import UnifiedLLMAdapter, LLMResponse, LLMConfig, LLMProvider
from core.secure_secrets_manager import SecureSecretsManager, SecretMetadata, LocalSecretsProvider
from core.intelligent_cache import IntelligentCache, LRUCache, CacheEntry
from core.observability_system import ObservabilitySystem, AlertSeverity, Alert
from core.agent_system import AgentSystem, Agent, AgentCategory


# ========== FIXTURES ==========

@pytest.fixture
def temp_dir():
    """Create temporary directory for tests"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_llm_response():
    """Mock LLM response"""
    return LLMResponse(
        content="Test response",
        provider="openai",
        model="gpt-4",
        tokens_used=100,
        latency=1.5,
        cost=0.002
    )


@pytest.fixture
async def llm_adapter():
    """Create LLM adapter for testing"""
    adapter = UnifiedLLMAdapter()
    # Mock providers
    adapter.providers = {
        'openai': AsyncMock(),
        'anthropic': AsyncMock(),
        'gemini': AsyncMock()
    }
    return adapter


@pytest.fixture
async def secrets_manager(temp_dir):
    """Create secrets manager for testing"""
    return SecureSecretsManager(
        provider='local',
        config={'local_dir': temp_dir}
    )


@pytest.fixture
async def cache():
    """Create cache for testing"""
    cache = IntelligentCache({
        'local_maxsize': 100,
        'redis_enabled': False,
        'vector_enabled': False
    })
    return cache


@pytest.fixture
def observability():
    """Create observability system for testing"""
    return ObservabilitySystem({
        'metrics_enabled': True,
        'service_name': 'test'
    })


@pytest.fixture
def agent_system():
    """Create agent system for testing"""
    return AgentSystem()


# ========== LLM ADAPTER TESTS ==========

class TestUnifiedLLMAdapter:
    """Test unified LLM adapter"""
    
    @pytest.mark.asyncio
    async def test_query_auto_provider(self, llm_adapter, mock_llm_response):
        """Test automatic provider selection"""
        # Setup mock
        llm_adapter.providers['openai'].query = AsyncMock(return_value=mock_llm_response)
        llm_adapter.providers['openai'].validate = Mock(return_value=True)
        
        # Execute query
        response = await llm_adapter.query("Test prompt", provider='auto')
        
        # Verify
        assert response.content == "Test response"
        assert response.provider == "openai"
        llm_adapter.providers['openai'].query.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_query_with_fallback(self, llm_adapter):
        """Test fallback mechanism"""
        # Setup mocks - first provider fails, second succeeds
        error_response = LLMResponse(content="", provider="openai", model="", error="API error")
        success_response = LLMResponse(content="Success", provider="anthropic", model="claude")
        
        llm_adapter.providers['openai'].query = AsyncMock(return_value=error_response)
        llm_adapter.providers['openai'].validate = Mock(return_value=True)
        llm_adapter.providers['anthropic'].query = AsyncMock(return_value=success_response)
        llm_adapter.providers['anthropic'].validate = Mock(return_value=True)
        
        # Execute query
        response = await llm_adapter.query("Test prompt", provider='auto')
        
        # Verify fallback worked
        assert response.content == "Success"
        assert response.provider == "anthropic"
    
    @pytest.mark.asyncio
    async def test_consensus(self, llm_adapter):
        """Test multi-LLM consensus"""
        # Setup mock responses
        responses = [
            LLMResponse(content="Response A", provider="openai", model="gpt-4"),
            LLMResponse(content="Response B", provider="anthropic", model="claude"),
            LLMResponse(content="Response C", provider="gemini", model="gemini")
        ]
        
        for i, provider in enumerate(['openai', 'anthropic', 'gemini']):
            llm_adapter.providers[provider].query = AsyncMock(return_value=responses[i])
            llm_adapter.providers[provider].validate = Mock(return_value=True)
        
        # Execute consensus
        result = await llm_adapter.consensus("Test prompt")
        
        # Verify
        assert result['consensus'] is not None
        assert 'confidence' in result
        assert len(result['responses']) == 3
    
    def test_metrics_tracking(self, llm_adapter):
        """Test metrics are tracked correctly"""
        initial_queries = llm_adapter.metrics['total_queries']
        
        # Simulate successful query
        llm_adapter.metrics['total_queries'] += 1
        llm_adapter.metrics['successful_queries'] += 1
        llm_adapter.metrics['total_cost'] += 0.002
        
        # Verify metrics
        metrics = llm_adapter.get_metrics()
        assert metrics['total_queries'] == initial_queries + 1
        assert metrics['successful_queries'] >= 1
        assert metrics['total_cost'] >= 0.002


# ========== SECRETS MANAGER TESTS ==========

class TestSecureSecretsManager:
    """Test secure secrets manager"""
    
    @pytest.mark.asyncio
    async def test_set_and_get_secret(self, secrets_manager):
        """Test setting and getting secrets"""
        # Set secret
        success = await secrets_manager.set_secret('test-key', 'test-value')
        assert success
        
        # Get secret
        value = await secrets_manager.get_secret('test-key')
        assert value == 'test-value'
    
    @pytest.mark.asyncio
    async def test_secret_caching(self, secrets_manager):
        """Test secret caching"""
        # Set secret
        await secrets_manager.set_secret('cached-key', 'cached-value')
        
        # First get - from provider
        value1 = await secrets_manager.get_secret('cached-key')
        assert value1 == 'cached-value'
        
        # Second get - should be from cache
        value2 = await secrets_manager.get_secret('cached-key')
        assert value2 == 'cached-value'
    
    @pytest.mark.asyncio
    async def test_secret_rotation(self, secrets_manager):
        """Test secret rotation"""
        # Set initial secret
        await secrets_manager.set_secret('rotate-key', 'old-value')
        
        # Rotate secret
        success = await secrets_manager.rotate_secret('rotate-key', 'new-value')
        assert success
        
        # Verify new value
        value = await secrets_manager.get_secret('rotate-key')
        assert value == 'new-value'
    
    @pytest.mark.asyncio
    async def test_api_keys_retrieval(self, secrets_manager):
        """Test API keys retrieval"""
        # Set API keys
        await secrets_manager.set_secret('openai-api-key', 'sk-test123')
        await secrets_manager.set_secret('anthropic-api-key', 'sk-ant-test')
        
        # Get API keys
        api_keys = await secrets_manager.get_api_keys()
        
        # Verify
        assert api_keys['openai'] == 'sk-test123'
        assert api_keys['anthropic'] == 'sk-ant-test'
    
    def test_audit_logging(self, secrets_manager):
        """Test audit logging"""
        # Simulate access
        secrets_manager._log_access('test-secret', 'get')
        secrets_manager._log_access('test-secret', 'set')
        
        # Check audit log
        log = secrets_manager.get_audit_log('test-secret')
        assert len(log) >= 2
        assert any(entry['action'] == 'get' for entry in log)
        assert any(entry['action'] == 'set' for entry in log)


# ========== CACHE TESTS ==========

class TestIntelligentCache:
    """Test intelligent cache system"""
    
    @pytest.mark.asyncio
    async def test_multi_level_caching(self, cache):
        """Test multi-level cache operations"""
        # Set value
        await cache.set('test-key', 'test-value', ttl=60)
        
        # Get value - should be from L1
        value = await cache.get('test-key')
        assert value == 'test-value'
        assert cache.stats['l1_hits'] > 0
    
    @pytest.mark.asyncio
    async def test_cache_invalidation(self, cache):
        """Test cache invalidation"""
        # Set value
        await cache.set('invalid-key', 'value', ttl=60)
        
        # Invalidate
        success = await cache.invalidate('invalid-key')
        assert success
        
        # Try to get - should be None
        value = await cache.get('invalid-key')
        assert value is None
    
    @pytest.mark.asyncio
    async def test_get_or_compute(self, cache):
        """Test get_or_compute functionality"""
        compute_called = False
        
        async def compute_fn():
            nonlocal compute_called
            compute_called = True
            return 'computed-value'
        
        # First call - should compute
        value1 = await cache.get_or_compute('compute-key', compute_fn)
        assert value1 == 'computed-value'
        assert compute_called
        
        # Second call - should use cache
        compute_called = False
        value2 = await cache.get_or_compute('compute-key', compute_fn)
        assert value2 == 'computed-value'
        assert not compute_called
    
    def test_lru_cache_eviction(self):
        """Test LRU cache eviction"""
        cache = LRUCache(maxsize=3)
        
        # Fill cache
        cache.set('key1', 'value1')
        cache.set('key2', 'value2')
        cache.set('key3', 'value3')
        
        # Add one more - should evict key1
        cache.set('key4', 'value4')
        
        # Verify eviction
        assert cache.get('key1') is None
        assert cache.get('key4') == 'value4'
        assert cache.evictions > 0
    
    def test_cache_statistics(self, cache):
        """Test cache statistics"""
        # Perform operations
        cache.local_cache.set('stat-key', 'value')
        cache.local_cache.get('stat-key')  # Hit
        cache.local_cache.get('missing')   # Miss
        
        # Get stats
        stats = cache.get_stats()
        
        # Verify
        assert stats['l1_stats']['hits'] > 0
        assert stats['l1_stats']['misses'] > 0
        assert 'hit_rate' in stats['l1_stats']


# ========== OBSERVABILITY TESTS ==========

class TestObservabilitySystem:
    """Test observability system"""
    
    def test_track_operation(self, observability):
        """Test operation tracking"""
        with observability.track_operation('test_op', tags=['test']):
            # Simulate operation
            pass
        
        # Check metrics
        assert 'test_op' in observability.performance_stats
        assert len(observability.performance_stats['test_op']) > 0
    
    @pytest.mark.asyncio
    async def test_async_operation_tracking(self, observability):
        """Test async operation tracking"""
        async with observability.track_async_operation('async_op'):
            await asyncio.sleep(0.01)
        
        # Check metrics
        assert 'async_op' in observability.performance_stats
    
    @pytest.mark.asyncio
    async def test_alert_triggering(self, observability):
        """Test alert triggering"""
        # Trigger alert
        await observability.alerts.trigger(
            'test_alert',
            'Test message',
            AlertSeverity.WARNING
        )
        
        # Check active alerts
        active = observability.alerts.get_active_alerts()
        assert len(active) > 0
        assert any(a.name == 'test_alert' for a in active)
    
    def test_health_checks(self, observability):
        """Test health check system"""
        # Add health check
        observability.add_health_check(
            'test_service',
            lambda: True
        )
        
        # Run health checks
        asyncio.run(self._run_health_check(observability))
    
    async def _run_health_check(self, observability):
        results = await observability.check_health()
        assert 'test_service' in results
        assert results['test_service'].status == 'healthy'
    
    def test_metrics_export(self, observability):
        """Test metrics export"""
        # Track some metrics
        observability.track_llm_call(
            provider='openai',
            model='gpt-4',
            tokens_in=100,
            tokens_out=200,
            latency=1.5,
            cost=0.003,
            success=True
        )
        
        # Get metrics summary
        summary = observability.get_metrics_summary()
        assert 'performance' in summary


# ========== AGENT SYSTEM TESTS ==========

class TestAgentSystem:
    """Test agent system"""
    
    def test_agent_initialization(self, agent_system):
        """Test all 39 agents are initialized"""
        agents = agent_system.list_agents()
        assert len(agents) == 39
        
        # Check categories
        categories = set(agent.category for agent in agents)
        assert AgentCategory.CORE_ENGINEERING in categories
        assert AgentCategory.AUTOMATION in categories
        assert AgentCategory.CLOUD_PLATFORMS in categories
        assert AgentCategory.ADVANCED in categories
        assert AgentCategory.DOMAIN_SPECIFIC in categories
    
    def test_agent_selection(self, agent_system):
        """Test intelligent agent selection"""
        # Test backend query
        agent = agent_system.select_agent("How to create a REST API?")
        assert agent.name == 'backend'
        
        # Test cloud query
        agent = agent_system.select_agent("Deploy to AWS Lambda")
        assert agent.name in ['aws', 'serverless']
        
        # Test AI/ML query
        agent = agent_system.select_agent("Train a neural network")
        assert agent.name == 'ai-ml'
    
    @pytest.mark.asyncio
    async def test_agent_processing(self, agent_system):
        """Test agent query processing"""
        agent = agent_system.get_agent('backend')
        assert agent is not None
        
        # Process query
        response = await agent.process(
            "Create API endpoint",
            "Here's a basic endpoint"
        )
        
        # Verify response is enhanced
        assert len(response) > 0
        assert 'backend' in response.lower() or 'api' in response.lower()
    
    def test_agent_search(self, agent_system):
        """Test agent search functionality"""
        # Search for Docker-related agents
        docker_agents = agent_system.search_agents('docker')
        assert len(docker_agents) > 0
        assert any(a.name == 'docker' for a in docker_agents)
        
        # Search for cloud agents
        cloud_agents = agent_system.search_agents('cloud')
        assert len(cloud_agents) >= 5
    
    def test_agent_categories(self, agent_system):
        """Test agent categorization"""
        # Get agents by category
        core_agents = agent_system.list_agents_by_category(AgentCategory.CORE_ENGINEERING)
        assert len(core_agents) == 10
        
        automation_agents = agent_system.list_agents_by_category(AgentCategory.AUTOMATION)
        assert len(automation_agents) == 7
        
        cloud_agents = agent_system.list_agents_by_category(AgentCategory.CLOUD_PLATFORMS)
        assert len(cloud_agents) == 9


# ========== INTEGRATION TESTS ==========

class TestIntegration:
    """Integration tests for complete system"""
    
    @pytest.mark.asyncio
    async def test_full_query_pipeline(self):
        """Test complete query pipeline"""
        # Create components
        secrets_manager = SecureSecretsManager(provider='local')
        cache = IntelligentCache({'redis_enabled': False})
        llm_adapter = UnifiedLLMAdapter(cache_manager=cache, secrets_manager=secrets_manager)
        agent_system = AgentSystem(llm_adapter=llm_adapter, cache=cache)
        
        # Mock LLM response
        with patch.object(llm_adapter, 'query') as mock_query:
            mock_query.return_value = LLMResponse(
                content="API implementation",
                provider="mock",
                model="mock-model"
            )
            
            # Select agent and process
            agent = agent_system.select_agent("Create REST API")
            assert agent is not None
            
            # Process query
            response = await agent.process("Create REST API", "Basic API")
            assert len(response) > 0
    
    @pytest.mark.asyncio
    async def test_caching_with_llm(self):
        """Test caching integration with LLM"""
        cache = IntelligentCache({'redis_enabled': False})
        llm_adapter = UnifiedLLMAdapter(cache_manager=cache)
        
        # Mock provider
        mock_response = LLMResponse(content="Cached response", provider="test", model="test")
        llm_adapter.providers['test'] = AsyncMock()
        llm_adapter.providers['test'].query = AsyncMock(return_value=mock_response)
        
        # First query - should call provider
        response1 = await llm_adapter.query("Test prompt", provider='test')
        assert response1.content == "Cached response"
        llm_adapter.providers['test'].query.assert_called_once()
        
        # Second query - should use cache
        llm_adapter.providers['test'].query.reset_mock()
        response2 = await llm_adapter.query("Test prompt", provider='test')
        assert response2.content == "Cached response"
        # Provider should not be called again due to cache
    
    @pytest.mark.asyncio
    async def test_observability_integration(self):
        """Test observability with other components"""
        obs = ObservabilitySystem()
        cache = IntelligentCache({'redis_enabled': False})
        
        # Track cache operations
        async with obs.track_async_operation('cache_test'):
            await cache.set('obs-key', 'obs-value')
            value = await cache.get('obs-key')
            assert value == 'obs-value'
        
        # Check metrics
        summary = obs.get_metrics_summary()
        assert 'cache_test' in summary['performance']


# ========== PERFORMANCE TESTS ==========

class TestPerformance:
    """Performance and stress tests"""
    
    @pytest.mark.asyncio
    async def test_concurrent_queries(self, llm_adapter):
        """Test concurrent query handling"""
        # Mock provider
        llm_adapter.providers['test'] = AsyncMock()
        llm_adapter.providers['test'].query = AsyncMock(
            return_value=LLMResponse(content="Response", provider="test", model="test")
        )
        llm_adapter.providers['test'].validate = Mock(return_value=True)
        
        # Execute concurrent queries
        tasks = [
            llm_adapter.query(f"Query {i}", provider='test')
            for i in range(10)
        ]
        responses = await asyncio.gather(*tasks)
        
        # Verify all completed
        assert len(responses) == 10
        assert all(r.content == "Response" for r in responses)
    
    def test_cache_performance(self):
        """Test cache performance with many items"""
        cache = LRUCache(maxsize=1000)
        
        # Add many items
        for i in range(1000):
            cache.set(f'key-{i}', f'value-{i}')
        
        # Verify performance
        assert len(cache.cache) == 1000
        
        # Test retrieval speed
        import time
        start = time.time()
        for i in range(100):
            cache.get(f'key-{i}')
        elapsed = time.time() - start
        
        # Should be very fast (< 10ms for 100 gets)
        assert elapsed < 0.01
    
    @pytest.mark.asyncio
    async def test_secret_manager_performance(self, temp_dir):
        """Test secret manager with many secrets"""
        manager = SecureSecretsManager(
            provider='local',
            config={'local_dir': temp_dir}
        )
        
        # Add many secrets
        for i in range(100):
            await manager.set_secret(f'secret-{i}', f'value-{i}')
        
        # Test retrieval performance
        import time
        start = time.time()
        
        # Get multiple secrets
        for i in range(50):
            value = await manager.get_secret(f'secret-{i}')
            assert value == f'value-{i}'
        
        elapsed = time.time() - start
        
        # Should complete within reasonable time
        assert elapsed < 1.0  # Less than 1 second for 50 gets


# ========== RUN TESTS ==========

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
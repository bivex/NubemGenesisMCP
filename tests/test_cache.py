"""
Integration tests for cache system
"""

import asyncio
import pytest
import time
from pathlib import Path
import sys

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.cache_system import MultiLevelCache, SmartCache, CacheStats


class TestCacheSystem:
    """Test multi-level cache system"""
    
    @pytest.fixture
    async def cache(self):
        """Create cache instance for testing"""
        cache = SmartCache(
            redis_url="redis://localhost:6379/1",  # Use different DB for tests
            l1_max_size=100,
            default_ttl=60,
            namespace="test"
        )
        await cache.initialize()
        yield cache
        await cache.clear()
        await cache.close()
    
    @pytest.mark.asyncio
    async def test_basic_get_set(self, cache):
        """Test basic get and set operations"""
        # Set a value
        key = "test_key"
        value = {"data": "test_value", "number": 42}
        
        result = await cache.set(key, value, ttl=30)
        assert result is True
        
        # Get the value
        retrieved = await cache.get(key)
        assert retrieved == value
        
        # Get non-existent key
        missing = await cache.get("missing_key", default="default")
        assert missing == "default"
    
    @pytest.mark.asyncio
    async def test_l1_cache_hit(self, cache):
        """Test L1 (memory) cache hits"""
        key = "l1_test"
        value = "test_data"
        
        # Set value (goes to L1 and L2)
        await cache.set(key, value)
        
        # First get should hit L1
        stats_before = cache.stats.l1_hits
        result = await cache.get(key)
        stats_after = cache.stats.l1_hits
        
        assert result == value
        assert stats_after > stats_before
    
    @pytest.mark.asyncio
    async def test_ttl_expiration(self, cache):
        """Test TTL expiration"""
        key = "ttl_test"
        value = "expires_soon"
        
        # Set with very short TTL
        await cache.set(key, value, ttl=1)
        
        # Should exist immediately
        assert await cache.get(key) == value
        
        # Wait for expiration
        await asyncio.sleep(2)
        
        # Should be expired
        assert await cache.get(key) is None
    
    @pytest.mark.asyncio
    async def test_delete_operation(self, cache):
        """Test delete operation"""
        key = "delete_test"
        value = "to_be_deleted"
        
        await cache.set(key, value)
        assert await cache.get(key) == value
        
        # Delete the key
        deleted = await cache.delete(key)
        assert deleted is True
        
        # Should not exist
        assert await cache.get(key) is None
    
    @pytest.mark.asyncio
    async def test_mget_mset(self, cache):
        """Test multiple get/set operations"""
        items = {
            "key1": "value1",
            "key2": {"nested": "data"},
            "key3": [1, 2, 3]
        }
        
        # Set multiple
        result = await cache.mset(items, ttl=60)
        assert result is True
        
        # Get multiple
        keys = list(items.keys())
        results = await cache.mget(keys)
        
        for key in keys:
            assert key in results
            assert results[key] == items[key]
    
    @pytest.mark.asyncio
    async def test_get_or_set(self, cache):
        """Test get_or_set functionality"""
        key = "compute_test"
        expected = {"computed": "value"}
        
        async def generator():
            # Simulate expensive computation
            await asyncio.sleep(0.1)
            return expected
        
        # First call should compute
        start = time.time()
        result1 = await cache.get_or_set(key, generator, ttl=60)
        duration1 = time.time() - start
        
        assert result1 == expected
        assert duration1 >= 0.1  # Should take time to compute
        
        # Second call should hit cache
        start = time.time()
        result2 = await cache.get_or_set(key, generator, ttl=60)
        duration2 = time.time() - start
        
        assert result2 == expected
        assert duration2 < 0.05  # Should be fast from cache
    
    @pytest.mark.asyncio
    async def test_cache_stats(self, cache):
        """Test cache statistics"""
        # Perform some operations
        await cache.set("stat_test1", "value1")
        await cache.get("stat_test1")  # Hit
        await cache.get("missing")  # Miss
        await cache.delete("stat_test1")
        
        stats = await cache.get_stats()
        
        assert stats["hits"] > 0
        assert stats["misses"] > 0
        assert stats["sets"] > 0
        assert stats["deletes"] > 0
        assert "hit_rate" in stats
    
    @pytest.mark.asyncio
    async def test_decorator(self, cache):
        """Test cache decorator"""
        call_count = 0
        
        @cache.decorator.cached(ttl=60, key_prefix="decorated")
        async def expensive_function(param1, param2):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)
            return f"{param1}-{param2}-result"
        
        # First call
        result1 = await expensive_function("a", "b")
        assert call_count == 1
        
        # Second call with same params (should hit cache)
        result2 = await expensive_function("a", "b")
        assert call_count == 1  # Should not increment
        assert result1 == result2
        
        # Different params (should compute)
        result3 = await expensive_function("c", "d")
        assert call_count == 2
        assert result3 != result1
    
    @pytest.mark.asyncio
    async def test_clear_pattern(self, cache):
        """Test clearing by pattern"""
        # Set multiple keys
        await cache.set("user:1", "data1")
        await cache.set("user:2", "data2")
        await cache.set("post:1", "post_data")
        
        # Clear user keys
        await cache.clear("user:*")
        
        # User keys should be gone
        assert await cache.get("user:1") is None
        assert await cache.get("user:2") is None
        
        # Post key should remain
        assert await cache.get("post:1") == "post_data"


class TestCachePerformance:
    """Performance tests for cache system"""
    
    @pytest.mark.asyncio
    async def test_cache_performance(self):
        """Test cache performance metrics"""
        cache = SmartCache(
            redis_url="redis://localhost:6379/2",
            l1_max_size=1000,
            namespace="perf"
        )
        await cache.initialize()
        
        try:
            # Measure set performance
            start = time.time()
            for i in range(100):
                await cache.set(f"perf_key_{i}", {"value": i})
            set_duration = time.time() - start
            set_rate = 100 / set_duration
            
            # Measure get performance (L1 hits)
            start = time.time()
            for i in range(100):
                await cache.get(f"perf_key_{i}")
            get_duration = time.time() - start
            get_rate = 100 / get_duration
            
            print(f"\nCache Performance:")
            print(f"  Set rate: {set_rate:.0f} ops/sec")
            print(f"  Get rate: {get_rate:.0f} ops/sec")
            
            # Performance assertions
            assert set_rate > 100  # Should handle >100 sets/sec
            assert get_rate > 1000  # Should handle >1000 gets/sec
            
        finally:
            await cache.clear()
            await cache.close()


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])
"""
Advanced Multi-Level Cache System for NubemSuperFClaude
Implements L1 (memory), L2 (Redis), and L3 (Database) caching
"""

import asyncio
import json
import time
import hashlib
from typing import Any, Optional, Dict, List, Union
from datetime import datetime, timedelta
from functools import wraps
from core.safe_serialization import safe_dumps, safe_loads, safe_dumps_bytes, safe_loads_bytes
from collections import OrderedDict
import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool
import logging

logger = logging.getLogger(__name__)


class CacheStats:
    """Track cache statistics"""
    
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.deletes = 0
        self.l1_hits = 0
        self.l2_hits = 0
        self.l3_hits = 0
        
    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0
    
    def to_dict(self) -> Dict:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "sets": self.sets,
            "deletes": self.deletes,
            "hit_rate": f"{self.hit_rate:.2f}%",
            "l1_hits": self.l1_hits,
            "l2_hits": self.l2_hits,
            "l3_hits": self.l3_hits
        }


class LRUCache:
    """Thread-safe LRU cache implementation for L1"""
    
    def __init__(self, max_size: int = 1000):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Any]:
        async with self.lock:
            if key not in self.cache:
                return None
            # Move to end (most recently used)
            self.cache.move_to_end(key)
            value, expiry = self.cache[key]
            if expiry and time.time() > expiry:
                del self.cache[key]
                return None
            return value
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        async with self.lock:
            expiry = time.time() + ttl if ttl else None
            self.cache[key] = (value, expiry)
            self.cache.move_to_end(key)
            # Remove oldest if over limit
            if len(self.cache) > self.max_size:
                self.cache.popitem(last=False)
    
    async def delete(self, key: str) -> bool:
        async with self.lock:
            if key in self.cache:
                del self.cache[key]
                return True
            return False
    
    async def clear(self):
        async with self.lock:
            self.cache.clear()
    
    async def size(self) -> int:
        async with self.lock:
            return len(self.cache)


class MultiLevelCache:
    """Multi-level cache with L1 (memory), L2 (Redis), L3 (Database)"""
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        l1_max_size: int = 1000,
        default_ttl: int = 3600,
        namespace: str = "nubemsuper"
    ):
        self.l1_cache = LRUCache(max_size=l1_max_size)
        self.redis_url = redis_url
        self.redis_client = None
        self.redis_pool = None
        self.default_ttl = default_ttl
        self.namespace = namespace
        self.stats = CacheStats()
        self._initialized = False
    
    async def initialize(self):
        """Initialize Redis connection"""
        if self._initialized:
            return
        
        try:
            self.redis_pool = ConnectionPool.from_url(
                self.redis_url,
                max_connections=50,
                decode_responses=False
            )
            self.redis_client = redis.Redis(connection_pool=self.redis_pool)
            await self.redis_client.ping()
            self._initialized = True
            logger.info("Redis cache initialized successfully")
        except Exception as e:
            logger.warning(f"Redis initialization failed: {e}. Using L1 cache only.")
            self.redis_client = None
    
    async def close(self):
        """Close Redis connection"""
        if self.redis_pool:
            await self.redis_pool.disconnect()
    
    def _make_key(self, key: str) -> str:
        """Create namespaced key"""
        return f"{self.namespace}:{key}"
    
    def _serialize(self, value: Any) -> bytes:
        """Serialize value for storage"""
        return safe_dumps_bytes(value)
    
    def _deserialize(self, data: bytes) -> Any:
        """Deserialize value from storage"""
        return safe_loads_bytes(data)
    
    async def get(self, key: str, default: Any = None) -> Any:
        """Get value from cache (checks L1, then L2, then L3)"""
        full_key = self._make_key(key)
        
        # Check L1 (memory)
        value = await self.l1_cache.get(full_key)
        if value is not None:
            self.stats.hits += 1
            self.stats.l1_hits += 1
            logger.debug(f"L1 cache hit for key: {key}")
            return value
        
        # Check L2 (Redis)
        if self.redis_client:
            try:
                data = await self.redis_client.get(full_key)
                if data:
                    value = self._deserialize(data)
                    # Populate L1
                    await self.l1_cache.set(full_key, value, self.default_ttl)
                    self.stats.hits += 1
                    self.stats.l2_hits += 1
                    logger.debug(f"L2 cache hit for key: {key}")
                    return value
            except Exception as e:
                logger.error(f"Redis get error: {e}")
        
        # L3 would be database lookup (not implemented here)
        # This would be where you fetch from PostgreSQL/MongoDB
        
        self.stats.misses += 1
        logger.debug(f"Cache miss for key: {key}")
        return default
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        skip_l1: bool = False
    ) -> bool:
        """Set value in cache"""
        full_key = self._make_key(key)
        ttl = ttl or self.default_ttl
        
        try:
            # Set in L1 (memory)
            if not skip_l1:
                await self.l1_cache.set(full_key, value, ttl)
            
            # Set in L2 (Redis)
            if self.redis_client:
                data = self._serialize(value)
                await self.redis_client.setex(full_key, ttl, data)
            
            self.stats.sets += 1
            logger.debug(f"Cache set for key: {key} with TTL: {ttl}")
            return True
            
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete value from all cache levels"""
        full_key = self._make_key(key)
        
        # Delete from L1
        l1_deleted = await self.l1_cache.delete(full_key)
        
        # Delete from L2
        l2_deleted = False
        if self.redis_client:
            try:
                l2_deleted = await self.redis_client.delete(full_key) > 0
            except Exception as e:
                logger.error(f"Redis delete error: {e}")
        
        if l1_deleted or l2_deleted:
            self.stats.deletes += 1
            logger.debug(f"Cache delete for key: {key}")
            
        return l1_deleted or l2_deleted
    
    async def clear(self, pattern: Optional[str] = None):
        """Clear cache (optionally by pattern)"""
        # Clear L1
        if not pattern:
            await self.l1_cache.clear()
        
        # Clear L2
        if self.redis_client:
            try:
                if pattern:
                    cursor = b'0'
                    pattern_key = self._make_key(pattern)
                    while cursor:
                        cursor, keys = await self.redis_client.scan(
                            cursor, match=pattern_key
                        )
                        if keys:
                            await self.redis_client.delete(*keys)
                else:
                    await self.redis_client.flushdb()
            except Exception as e:
                logger.error(f"Redis clear error: {e}")
    
    async def get_stats(self) -> Dict:
        """Get cache statistics"""
        stats = self.stats.to_dict()
        stats["l1_size"] = await self.l1_cache.size()
        
        if self.redis_client:
            try:
                info = await self.redis_client.info("memory")
                stats["l2_memory"] = info.get("used_memory_human", "N/A")
            except:
                stats["l2_memory"] = "N/A"
        
        return stats
    
    async def mget(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple values at once"""
        results = {}
        
        # Try L1 first
        for key in keys:
            value = await self.get(key)
            if value is not None:
                results[key] = value
        
        return results
    
    async def mset(self, items: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Set multiple values at once"""
        success = True
        for key, value in items.items():
            if not await self.set(key, value, ttl):
                success = False
        return success


class CacheDecorator:
    """Decorator for caching function results"""
    
    def __init__(self, cache: MultiLevelCache):
        self.cache = cache
    
    def cached(
        self,
        ttl: Optional[int] = None,
        key_prefix: Optional[str] = None,
        skip_args: List[int] = None
    ):
        """Cache decorator for async functions"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Generate cache key
                cache_key_parts = [key_prefix or func.__name__]
                
                # Add args to key (skip specified indices)
                skip_args_set = set(skip_args or [])
                for i, arg in enumerate(args):
                    if i not in skip_args_set:
                        cache_key_parts.append(str(arg))
                
                # Add kwargs to key
                for k, v in sorted(kwargs.items()):
                    cache_key_parts.append(f"{k}={v}")
                
                cache_key = ":".join(cache_key_parts)
                
                # Try to get from cache
                cached_value = await self.cache.get(cache_key)
                if cached_value is not None:
                    return cached_value
                
                # Execute function
                result = await func(*args, **kwargs)
                
                # Store in cache
                await self.cache.set(cache_key, result, ttl)
                
                return result
            
            return wrapper
        return decorator


class SmartCache(MultiLevelCache):
    """Enhanced cache with smart features"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.decorator = CacheDecorator(self)
        self._warm_cache_tasks = []
    
    async def warm_cache(self, key: str, generator_func, ttl: Optional[int] = None):
        """Pre-populate cache with generated value"""
        value = await generator_func()
        await self.set(key, value, ttl)
        return value
    
    async def get_or_set(
        self,
        key: str,
        generator_func,
        ttl: Optional[int] = None
    ) -> Any:
        """Get from cache or generate and set if missing"""
        value = await self.get(key)
        if value is not None:
            return value
        
        value = await generator_func()
        await self.set(key, value, ttl)
        return value
    
    async def invalidate_pattern(self, pattern: str):
        """Invalidate all keys matching pattern"""
        await self.clear(pattern)
        logger.info(f"Invalidated cache keys matching pattern: {pattern}")
    
    def compute_key(self, *args, **kwargs) -> str:
        """Compute cache key from arguments"""
        key_parts = [str(arg) for arg in args]
        key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
        key_string = ":".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()


# Global cache instance
_cache_instance: Optional[SmartCache] = None


async def get_cache() -> SmartCache:
    """Get or create global cache instance"""
    global _cache_instance
    
    if _cache_instance is None:
        import os
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _cache_instance = SmartCache(redis_url=redis_url)
        await _cache_instance.initialize()
    
    return _cache_instance


async def close_cache():
    """Close global cache instance"""
    global _cache_instance
    if _cache_instance:
        await _cache_instance.close()
        _cache_instance = None


# Example usage functions
async def example_usage():
    """Example of how to use the cache system"""
    
    # Get cache instance
    cache = await get_cache()
    
    # Simple get/set
    await cache.set("user:123", {"name": "John", "age": 30}, ttl=300)
    user = await cache.get("user:123")
    
    # Using get_or_set
    async def fetch_expensive_data():
        # Simulate expensive operation
        await asyncio.sleep(1)
        return {"data": "expensive"}
    
    data = await cache.get_or_set("expensive_data", fetch_expensive_data, ttl=600)
    
    # Using decorator
    @cache.decorator.cached(ttl=300, key_prefix="api_response")
    async def get_api_response(endpoint: str, params: dict):
        # Simulate API call
        await asyncio.sleep(0.5)
        return {"endpoint": endpoint, "result": "data"}
    
    # This will be cached
    response1 = await get_api_response("/users", {"page": 1})
    # This will hit cache
    response2 = await get_api_response("/users", {"page": 1})
    
    # Get statistics
    stats = await cache.get_stats()
    print(f"Cache stats: {stats}")
    
    # Clean up
    await close_cache()


if __name__ == "__main__":
    asyncio.run(example_usage())
"""
Multi-tier caching system with Redis
Implements caching strategy recommended by ChatGPT and Gemini
"""

import hashlib
import json
from .safe_serialization import safe_dumps, safe_loads, safe_dumps_bytes, safe_loads_bytes
import time
import asyncio
import sys
from typing import Any, Optional, Dict, List, Callable
from datetime import datetime, timedelta
from collections import OrderedDict
import logging

logger = logging.getLogger(__name__)

class LRUCache:
    """Thread-safe LRU cache implementation with memory limits"""
    
    def __init__(self, capacity: int = 1000, max_memory_mb: int = 100):
        self.cache = OrderedDict()
        self.capacity = capacity
        self.max_memory_bytes = max_memory_mb * 1024 * 1024  # Convert MB to bytes
        self.current_memory_bytes = 0
        self.hits = 0
        self.misses = 0
        self._lock = asyncio.Lock()
    
    def _get_size(self, obj: Any) -> int:
        """Calculate memory size of object"""
        try:
            return sys.getsizeof(safe_dumps_bytes(obj))
        except:
            return sys.getsizeof(str(obj))
    
    async def _cleanup_memory(self):
        """Remove oldest items if memory limit exceeded"""
        while (self.current_memory_bytes > self.max_memory_bytes and 
               len(self.cache) > 0):
            # Remove oldest item
            key, item = self.cache.popitem(last=False)
            self.current_memory_bytes -= self._get_size(item)
            logger.debug(f"Removed cache item {key} due to memory limit")
    
    async def get(self, key: str) -> Optional[Any]:
        """Get item from cache"""
        async with self._lock:
            if key in self.cache:
                # Move to end (most recently used)
                self.cache.move_to_end(key)
                self.hits += 1
                return self.cache[key]['value']
            
            self.misses += 1
            return None
    
    async def set(self, key: str, value: Any, ttl: int = 3600):
        """Set item in cache with memory management"""
        async with self._lock:
            item = {
                'value': value,
                'expires_at': time.time() + ttl
            }
            item_size = self._get_size(item)
            
            # Remove existing item if updating
            if key in self.cache:
                old_item = self.cache[key]
                self.current_memory_bytes -= self._get_size(old_item)
                del self.cache[key]
            
            # Remove oldest if at capacity
            if len(self.cache) >= self.capacity:
                old_key, old_item = self.cache.popitem(last=False)
                self.current_memory_bytes -= self._get_size(old_item)
            
            # Add new item
            self.cache[key] = item
            self.current_memory_bytes += item_size
            
            # Check memory limits and cleanup if needed
            await self._cleanup_memory()
    
    async def invalidate(self, pattern: str = None):
        """Invalidate cache entries"""
        async with self._lock:
            if pattern:
                keys_to_remove = [k for k in self.cache if pattern in k]
                for key in keys_to_remove:
                    del self.cache[key]
            else:
                self.cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics including memory usage"""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        memory_usage_mb = self.current_memory_bytes / (1024 * 1024)
        memory_usage_pct = (self.current_memory_bytes / self.max_memory_bytes * 100)
        
        return {
            'size': len(self.cache),
            'capacity': self.capacity,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': round(hit_rate, 2),
            'memory_usage_mb': round(memory_usage_mb, 2),
            'memory_limit_mb': self.max_memory_bytes / (1024 * 1024),
            'memory_usage_pct': round(memory_usage_pct, 2)
        }

class RedisCache:
    """Redis cache wrapper with async support"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis_client = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize Redis connection"""
        if self._initialized:
            return
        
        try:
            # Using fakeredis for testing if redis is not available
            try:
                import redis.asyncio as redis
                self.redis_client = await redis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=50
                )
                await self.redis_client.ping()
                logger.info("Redis cache initialized")
            except:
                # Fallback to in-memory cache if Redis not available
                logger.warning("Redis not available, using in-memory fallback")
                self.redis_client = None
            
            self._initialized = True
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis: {e}")
            self.redis_client = None
            self._initialized = True
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from Redis"""
        if not self.redis_client:
            return None
        
        try:
            value = await self.redis_client.get(key)
            return value
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None
    
    async def set(self, key: str, value: str, ttl: int = 3600):
        """Set value in Redis"""
        if not self.redis_client:
            return
        
        try:
            await self.redis_client.setex(key, ttl, value)
        except Exception as e:
            logger.error(f"Redis set error: {e}")
    
    async def delete(self, pattern: str):
        """Delete keys matching pattern"""
        if not self.redis_client:
            return
        
        try:
            cursor = 0
            while True:
                cursor, keys = await self.redis_client.scan(
                    cursor,
                    match=f"*{pattern}*"
                )
                if keys:
                    await self.redis_client.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.error(f"Redis delete error: {e}")

class CacheManager:
    """
    Multi-tier caching system with:
    - L1: In-memory LRU cache (sub-ms access)
    - L2: Redis cache (1-5ms access)
    - L3: Persistent cache (future: disk/database)
    
    Implements caching strategy from ChatGPT and Gemini recommendations
    """
    
    def __init__(self, 
                 redis_url: str = "redis://localhost:6379",
                 l1_capacity: int = 1000,
                 default_ttl: int = 3600):
        
        # L1: Memory cache
        self.l1_cache = LRUCache(capacity=l1_capacity)
        
        # L2: Redis cache
        self.l2_cache = RedisCache(redis_url)
        
        # Configuration
        self.default_ttl = default_ttl
        
        # Statistics
        self.stats = {
            'l1_requests': 0,
            'l2_requests': 0,
            'cache_writes': 0,
            'cache_invalidations': 0
        }
        
        self._initialized = False
    
    async def initialize(self):
        """Initialize cache layers"""
        if self._initialized:
            return
        
        await self.l2_cache.initialize()
        self._initialized = True
        logger.info("Cache manager initialized")
    
    def _generate_key(self, prefix: str, data: Any) -> str:
        """Generate cache key from data"""
        if isinstance(data, dict):
            data_str = json.dumps(data, sort_keys=True)
        else:
            data_str = str(data)
        
        hash_obj = hashlib.sha256(data_str.encode())
        return f"{prefix}:{hash_obj.hexdigest()[:16]}"
    
    async def get(self, 
                  key: str,
                  compute_fn: Optional[Callable] = None,
                  ttl: Optional[int] = None) -> Optional[Any]:
        """
        Get from cache with waterfall lookup:
        L1 -> L2 -> Compute (if function provided)
        """
        if not self._initialized:
            await self.initialize()
        
        ttl = ttl or self.default_ttl
        
        # Check L1 (memory)
        self.stats['l1_requests'] += 1
        value = await self.l1_cache.get(key)
        if value is not None:
            logger.debug(f"L1 cache hit: {key}")
            return value
        
        # Check L2 (Redis)
        self.stats['l2_requests'] += 1
        value_str = await self.l2_cache.get(key)
        if value_str is not None:
            logger.debug(f"L2 cache hit: {key}")
            try:
                value = json.loads(value_str)
                # Populate L1
                await self.l1_cache.set(key, value, ttl)
                return value
            except:
                # Try pickle for complex objects
                try:
                    value = safe_loads(value_str)
                    await self.l1_cache.set(key, value, ttl)
                    return value
                except:
                    pass
        
        # Cache miss - compute if function provided
        if compute_fn:
            logger.debug(f"Cache miss, computing: {key}")
            value = await compute_fn() if asyncio.iscoroutinefunction(compute_fn) else compute_fn()
            await self.set(key, value, ttl)
            return value
        
        return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set value in all cache tiers"""
        if not self._initialized:
            await self.initialize()
        
        ttl = ttl or self.default_ttl
        self.stats['cache_writes'] += 1
        
        # Set in L1 (memory)
        await self.l1_cache.set(key, value, ttl)
        
        # Set in L2 (Redis)
        try:
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value)
            else:
                value_str = safe_dumps(value)
            
            await self.l2_cache.set(key, value_str, ttl)
        except Exception as e:
            logger.error(f"Failed to cache in L2: {e}")
    
    async def invalidate(self, pattern: str = None):
        """Invalidate cache entries matching pattern"""
        if not self._initialized:
            await self.initialize()
        
        self.stats['cache_invalidations'] += 1
        
        # Invalidate L1
        await self.l1_cache.invalidate(pattern)
        
        # Invalidate L2
        if pattern:
            await self.l2_cache.delete(pattern)
    
    async def get_or_compute(self,
                            key: str,
                            compute_fn: Callable,
                            ttl: Optional[int] = None) -> Any:
        """Convenience method for get with compute"""
        return await self.get(key, compute_fn, ttl)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        l1_stats = self.l1_cache.get_stats()
        
        return {
            'l1': l1_stats,
            'l2': {
                'available': self.l2_cache.redis_client is not None
            },
            'manager': self.stats
        }
    
    async def warmup(self, keys_and_functions: Dict[str, Callable]):
        """Pre-populate cache with commonly used data"""
        for key, compute_fn in keys_and_functions.items():
            await self.get_or_compute(key, compute_fn)
        
        logger.info(f"Cache warmed up with {len(keys_and_functions)} entries")

# Global cache manager instance
global_cache_manager = CacheManager()

async def get_cache_manager() -> CacheManager:
    """Get the global cache manager instance"""
    if not global_cache_manager._initialized:
        await global_cache_manager.initialize()
    return global_cache_manager
#!/usr/bin/env python3
"""
Multi-Level Cache System for NubemSuperFClaude
L1: Memory Cache (Fast)
L2: Redis Cache (Distributed)
L3: Disk Cache (Persistent)
"""

import asyncio
import json
import hashlib
from .safe_serialization import safe_dumps, safe_loads, safe_dumps_bytes, safe_loads_bytes
import time
from typing import Any, Optional, Dict, Union
from dataclasses import dataclass
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

@dataclass
class CacheConfig:
    """Configuration for multi-level cache"""
    l1_max_size: int = 1000  # Max items in memory
    l1_ttl: int = 300  # 5 minutes
    l2_ttl: int = 3600  # 1 hour
    l3_ttl: int = 86400  # 24 hours
    l3_max_size_mb: int = 1000  # Max disk cache size
    cache_dir: str = "/tmp/nubem_cache"
    enable_compression: bool = True
    enable_stats: bool = True

@dataclass
class CacheStats:
    """Statistics for cache performance"""
    l1_hits: int = 0
    l1_misses: int = 0
    l2_hits: int = 0
    l2_misses: int = 0
    l3_hits: int = 0
    l3_misses: int = 0
    total_requests: int = 0
    avg_response_time: float = 0.0

class L1MemoryCache:
    """In-memory cache with LRU eviction"""
    
    def __init__(self, max_size: int = 1000, ttl: int = 300):
        self.max_size = max_size
        self.ttl = ttl
        self.cache: Dict[str, tuple] = {}
        self.access_order = []
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from L1 cache"""
        async with self._lock:
            if key in self.cache:
                value, timestamp = self.cache[key]
                if time.time() - timestamp < self.ttl:
                    # Move to end (most recently used)
                    self.access_order.remove(key)
                    self.access_order.append(key)
                    return value
                else:
                    # Expired
                    del self.cache[key]
                    self.access_order.remove(key)
            return None
    
    async def set(self, key: str, value: Any):
        """Set value in L1 cache"""
        async with self._lock:
            # Evict if at capacity
            if len(self.cache) >= self.max_size and key not in self.cache:
                # Remove least recently used
                lru_key = self.access_order.pop(0)
                del self.cache[lru_key]
            
            self.cache[key] = (value, time.time())
            if key in self.access_order:
                self.access_order.remove(key)
            self.access_order.append(key)
    
    async def invalidate(self, key: str):
        """Invalidate a cache entry"""
        async with self._lock:
            if key in self.cache:
                del self.cache[key]
                self.access_order.remove(key)
    
    def get_size(self) -> int:
        """Get current cache size"""
        return len(self.cache)

class L2RedisCache:
    """Redis-based distributed cache"""
    
    def __init__(self, ttl: int = 3600):
        self.ttl = ttl
        self.redis_client = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize Redis connection"""
        if self._initialized:
            return
        
        try:
            import redis.asyncio as aioredis
            self.redis_client = await aioredis.create_redis_pool(
                'redis://localhost:6379/1',
                minsize=5,
                maxsize=10
            )
            self._initialized = True
            logger.info("L2 Redis cache initialized")
        except Exception as e:
            logger.warning(f"Redis cache initialization failed: {e}")
            self.redis_client = None
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from L2 cache"""
        if not self.redis_client:
            return None
        
        try:
            value = await self.redis_client.get(f"nubem:cache:{key}")
            if value:
                return safe_loads_bytes(value)
        except Exception as e:
            logger.debug(f"L2 cache get error: {e}")
        return None
    
    async def set(self, key: str, value: Any):
        """Set value in L2 cache"""
        if not self.redis_client:
            return
        
        try:
            serialized = safe_dumps_bytes(value)
            await self.redis_client.setex(
                f"nubem:cache:{key}",
                self.ttl,
                serialized
            )
        except Exception as e:
            logger.debug(f"L2 cache set error: {e}")
    
    async def invalidate(self, key: str):
        """Invalidate a cache entry"""
        if not self.redis_client:
            return
        
        try:
            await self.redis_client.delete(f"nubem:cache:{key}")
        except Exception as e:
            logger.debug(f"L2 cache invalidate error: {e}")

class L3DiskCache:
    """Disk-based persistent cache"""
    
    def __init__(self, cache_dir: str = "/tmp/nubem_cache", ttl: int = 86400):
        self.cache_dir = Path(cache_dir)
        self.ttl = ttl
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_cache_path(self, key: str) -> Path:
        """Get file path for cache key"""
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{key_hash}.cache"
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from L3 cache"""
        cache_path = self._get_cache_path(key)
        
        if cache_path.exists():
            try:
                # Check if expired
                if time.time() - cache_path.stat().st_mtime < self.ttl:
                    with open(cache_path, 'rb') as f:
                        data = f.read()
                        return safe_loads_bytes(data)
                else:
                    # Expired, remove file
                    cache_path.unlink()
            except Exception as e:
                logger.debug(f"L3 cache get error: {e}")
        return None
    
    async def set(self, key: str, value: Any):
        """Set value in L3 cache"""
        cache_path = self._get_cache_path(key)
        
        try:
            with open(cache_path, 'wb') as f:
                f.write(safe_dumps_bytes(value))
        except Exception as e:
            logger.debug(f"L3 cache set error: {e}")
    
    async def invalidate(self, key: str):
        """Invalidate a cache entry"""
        cache_path = self._get_cache_path(key)
        
        if cache_path.exists():
            try:
                cache_path.unlink()
            except Exception as e:
                logger.debug(f"L3 cache invalidate error: {e}")
    
    def cleanup_old_entries(self):
        """Clean up expired cache entries"""
        current_time = time.time()
        for cache_file in self.cache_dir.glob("*.cache"):
            if current_time - cache_file.stat().st_mtime > self.ttl:
                try:
                    cache_file.unlink()
                except Exception:
                    pass

class MultiLevelCache:
    """Multi-level cache system with automatic fallback"""
    
    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        
        # Initialize cache levels
        self.l1 = L1MemoryCache(
            max_size=self.config.l1_max_size,
            ttl=self.config.l1_ttl
        )
        self.l2 = L2RedisCache(ttl=self.config.l2_ttl)
        self.l3 = L3DiskCache(
            cache_dir=self.config.cache_dir,
            ttl=self.config.l3_ttl
        )
        
        # Statistics
        self.stats = CacheStats() if self.config.enable_stats else None
        self._initialized = False
    
    async def initialize(self):
        """Initialize all cache levels"""
        if self._initialized:
            return
        
        await self.l2.initialize()
        
        # Start cleanup task for L3
        asyncio.create_task(self._cleanup_loop())
        
        self._initialized = True
        logger.info("Multi-level cache initialized")
    
    async def _cleanup_loop(self):
        """Periodic cleanup of expired entries"""
        while True:
            await asyncio.sleep(3600)  # Run every hour
            self.l3.cleanup_old_entries()
    
    def _generate_key(self, *args, **kwargs) -> str:
        """Generate cache key from arguments"""
        key_data = {
            'args': args,
            'kwargs': kwargs
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.sha256(key_str.encode()).hexdigest()
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache with automatic fallback"""
        start_time = time.time()
        
        if self.stats:
            self.stats.total_requests += 1
        
        # Try L1 (Memory)
        value = await self.l1.get(key)
        if value is not None:
            if self.stats:
                self.stats.l1_hits += 1
            logger.debug(f"L1 cache hit for {key[:8]}...")
            return value
        
        if self.stats:
            self.stats.l1_misses += 1
        
        # Try L2 (Redis)
        value = await self.l2.get(key)
        if value is not None:
            if self.stats:
                self.stats.l2_hits += 1
            logger.debug(f"L2 cache hit for {key[:8]}...")
            # Promote to L1
            await self.l1.set(key, value)
            return value
        
        if self.stats:
            self.stats.l2_misses += 1
        
        # Try L3 (Disk)
        value = await self.l3.get(key)
        if value is not None:
            if self.stats:
                self.stats.l3_hits += 1
            logger.debug(f"L3 cache hit for {key[:8]}...")
            # Promote to L1 and L2
            await self.l1.set(key, value)
            await self.l2.set(key, value)
            return value
        
        if self.stats:
            self.stats.l3_misses += 1
        
        # Update average response time
        if self.stats:
            response_time = time.time() - start_time
            self.stats.avg_response_time = (
                (self.stats.avg_response_time * (self.stats.total_requests - 1) + response_time) /
                self.stats.total_requests
            )
        
        return None
    
    async def set(self, key: str, value: Any, levels: Optional[list] = None):
        """Set value in cache levels"""
        if levels is None:
            levels = ['l1', 'l2', 'l3']
        
        tasks = []
        
        if 'l1' in levels:
            tasks.append(self.l1.set(key, value))
        if 'l2' in levels:
            tasks.append(self.l2.set(key, value))
        if 'l3' in levels:
            tasks.append(self.l3.set(key, value))
        
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.debug(f"Cache set for {key[:8]}... in levels: {levels}")
    
    async def invalidate(self, key: str):
        """Invalidate entry across all cache levels"""
        await asyncio.gather(
            self.l1.invalidate(key),
            self.l2.invalidate(key),
            self.l3.invalidate(key),
            return_exceptions=True
        )
        logger.debug(f"Cache invalidated for {key[:8]}...")
    
    def cache_decorator(self, ttl: Optional[int] = None):
        """Decorator for caching function results"""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                # Generate cache key
                cache_key = self._generate_key(func.__name__, *args, **kwargs)
                
                # Try to get from cache
                cached_value = await self.get(cache_key)
                if cached_value is not None:
                    return cached_value
                
                # Call function
                result = await func(*args, **kwargs)
                
                # Store in cache
                await self.set(cache_key, result)
                
                return result
            return wrapper
        return decorator
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get cache statistics"""
        if not self.stats:
            return {}
        
        total_hits = self.stats.l1_hits + self.stats.l2_hits + self.stats.l3_hits
        hit_rate = total_hits / self.stats.total_requests if self.stats.total_requests > 0 else 0
        
        return {
            'total_requests': self.stats.total_requests,
            'hit_rate': f"{hit_rate * 100:.2f}%",
            'l1': {
                'hits': self.stats.l1_hits,
                'misses': self.stats.l1_misses,
                'hit_rate': f"{(self.stats.l1_hits / self.stats.total_requests * 100) if self.stats.total_requests else 0:.2f}%",
                'size': self.l1.get_size()
            },
            'l2': {
                'hits': self.stats.l2_hits,
                'misses': self.stats.l2_misses,
                'hit_rate': f"{(self.stats.l2_hits / self.stats.total_requests * 100) if self.stats.total_requests else 0:.2f}%"
            },
            'l3': {
                'hits': self.stats.l3_hits,
                'misses': self.stats.l3_misses,
                'hit_rate': f"{(self.stats.l3_hits / self.stats.total_requests * 100) if self.stats.total_requests else 0:.2f}%"
            },
            'avg_response_time_ms': self.stats.avg_response_time * 1000
        }

# Global instance
_multi_cache: Optional[MultiLevelCache] = None

def get_multi_cache() -> MultiLevelCache:
    """Get or create global multi-level cache instance"""
    global _multi_cache
    if _multi_cache is None:
        _multi_cache = MultiLevelCache()
    return _multi_cache

async def initialize_cache():
    """Initialize global cache"""
    cache = get_multi_cache()
    await cache.initialize()
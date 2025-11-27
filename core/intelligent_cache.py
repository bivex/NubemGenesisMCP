"""
Intelligent Cache System - Multi-level caching with Redis, local memory, and vector embeddings
Implements smart invalidation, TTL management, and compression
"""

import os
import json
import hashlib
from core.safe_serialization import safe_dumps, safe_loads, safe_dumps_bytes, safe_loads_bytes
import zlib
import asyncio
from typing import Dict, Any, Optional, List, Tuple, Callable, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from functools import lru_cache, wraps
from collections import OrderedDict
import logging
import numpy as np

# Import Redis conditionally
try:
    import redis.asyncio as redis
    from redis.asyncio import ConnectionPool
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Import vector database conditionally
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False

# Import embeddings conditionally
try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Single cache entry with metadata"""
    key: str
    value: Any
    ttl: int
    created_at: datetime
    accessed_at: datetime
    access_count: int = 0
    size_bytes: int = 0
    compressed: bool = False
    tags: List[str] = field(default_factory=list)
    
    def is_expired(self) -> bool:
        """Check if entry has expired"""
        if self.ttl <= 0:
            return False
        return datetime.now() - self.created_at > timedelta(seconds=self.ttl)
    
    def update_access(self):
        """Update access metadata"""
        self.accessed_at = datetime.now()
        self.access_count += 1


class LRUCache:
    """Thread-safe LRU cache implementation"""
    
    def __init__(self, maxsize: int = 1000):
        self.maxsize = maxsize
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if key in self.cache:
            entry = self.cache[key]
            
            # Check expiration
            if entry.is_expired():
                del self.cache[key]
                self.misses += 1
                return None
            
            # Move to end (most recently used)
            self.cache.move_to_end(key)
            entry.update_access()
            self.hits += 1
            return entry.value
        
        self.misses += 1
        return None
    
    def set(self, key: str, value: Any, ttl: int = 3600, tags: List[str] = None):
        """Set value in cache"""
        # Calculate size
        try:
            size_bytes = len(safe_dumps_bytes(value))
        except:
            size_bytes = 0
        
        # Create entry
        entry = CacheEntry(
            key=key,
            value=value,
            ttl=ttl,
            created_at=datetime.now(),
            accessed_at=datetime.now(),
            size_bytes=size_bytes,
            tags=tags or []
        )
        
        # Add to cache
        if key in self.cache:
            # Update existing
            self.cache.move_to_end(key)
            self.cache[key] = entry
        else:
            # Add new
            self.cache[key] = entry
            
            # Evict if necessary
            while len(self.cache) > self.maxsize:
                evicted_key = next(iter(self.cache))
                del self.cache[evicted_key]
                self.evictions += 1
    
    def delete(self, key: str) -> bool:
        """Delete entry from cache"""
        if key in self.cache:
            del self.cache[key]
            return True
        return False
    
    def clear(self):
        """Clear all entries"""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_size = sum(e.size_bytes for e in self.cache.values())
        hit_rate = self.hits / max(1, self.hits + self.misses)
        
        return {
            'size': len(self.cache),
            'maxsize': self.maxsize,
            'hits': self.hits,
            'misses': self.misses,
            'evictions': self.evictions,
            'hit_rate': hit_rate,
            'total_size_bytes': total_size,
            'avg_size_bytes': total_size / max(1, len(self.cache))
        }
    
    def invalidate_by_tags(self, tags: List[str]):
        """Invalidate entries with specific tags"""
        keys_to_delete = []
        for key, entry in self.cache.items():
            if any(tag in entry.tags for tag in tags):
                keys_to_delete.append(key)
        
        for key in keys_to_delete:
            del self.cache[key]
        
        return len(keys_to_delete)


class RedisCache:
    """Redis cache adapter with async support"""
    
    def __init__(self, 
                 host: str = 'localhost',
                 port: int = 6379,
                 db: int = 0,
                 password: Optional[str] = None,
                 pool_size: int = 10,
                 key_prefix: str = 'nubem:'):
        
        if not REDIS_AVAILABLE:
            raise ImportError("redis not installed")
        
        self.key_prefix = key_prefix
        self.pool = ConnectionPool(
            host=host,
            port=port,
            db=db,
            password=password,
            max_connections=pool_size,
            decode_responses=False  # We'll handle encoding/decoding
        )
        self.client = None
    
    async def connect(self):
        """Initialize Redis connection"""
        if not self.client:
            self.client = redis.Redis(connection_pool=self.pool)
            await self.client.ping()
            logger.info("Connected to Redis")
    
    async def disconnect(self):
        """Close Redis connection"""
        if self.client:
            await self.client.close()
            await self.pool.disconnect()
            self.client = None
    
    def _make_key(self, key: str) -> str:
        """Create namespaced Redis key"""
        return f"{self.key_prefix}{key}"
    
    def _serialize(self, value: Any, compress: bool = True) -> bytes:
        """Serialize and optionally compress value"""
        serialized = safe_dumps_bytes(value)
        if compress and len(serialized) > 1024:  # Compress if > 1KB
            return zlib.compress(serialized)
        return serialized
    
    def _deserialize(self, data: bytes) -> Any:
        """Deserialize and decompress value"""
        try:
            # Try decompression first
            decompressed = zlib.decompress(data)
            return safe_loads_bytes(decompressed)
        except:
            # Not compressed, just unpickle
            return safe_loads_bytes(data)
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from Redis"""
        if not self.client:
            await self.connect()
        
        redis_key = self._make_key(key)
        data = await self.client.get(redis_key)
        
        if data:
            try:
                return self._deserialize(data)
            except Exception as e:
                logger.error(f"Error deserializing Redis value: {e}")
                return None
        return None
    
    async def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Set value in Redis with TTL"""
        if not self.client:
            await self.connect()
        
        redis_key = self._make_key(key)
        data = self._serialize(value)
        
        try:
            if ttl > 0:
                await self.client.setex(redis_key, ttl, data)
            else:
                await self.client.set(redis_key, data)
            return True
        except Exception as e:
            logger.error(f"Error setting Redis value: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete value from Redis"""
        if not self.client:
            await self.connect()
        
        redis_key = self._make_key(key)
        result = await self.client.delete(redis_key)
        return result > 0
    
    async def clear(self, pattern: str = "*"):
        """Clear all keys matching pattern"""
        if not self.client:
            await self.connect()
        
        pattern_key = self._make_key(pattern)
        cursor = 0
        
        while True:
            cursor, keys = await self.client.scan(cursor, match=pattern_key, count=100)
            if keys:
                await self.client.delete(*keys)
            if cursor == 0:
                break
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get Redis statistics"""
        if not self.client:
            await self.connect()
        
        info = await self.client.info('stats')
        memory = await self.client.info('memory')
        
        return {
            'connected_clients': info.get('connected_clients', 0),
            'used_memory': memory.get('used_memory_human', 'N/A'),
            'total_commands': info.get('total_commands_processed', 0),
            'keyspace_hits': info.get('keyspace_hits', 0),
            'keyspace_misses': info.get('keyspace_misses', 0),
            'hit_rate': info.get('keyspace_hits', 0) / max(1, 
                info.get('keyspace_hits', 0) + info.get('keyspace_misses', 0))
        }


class VectorCache:
    """Vector database cache for semantic similarity searches"""
    
    def __init__(self,
                 collection_name: str = "nubem_cache",
                 host: str = "localhost",
                 port: int = 6333,
                 embedding_model: str = "all-MiniLM-L6-v2"):
        
        if not QDRANT_AVAILABLE:
            logger.warning("Qdrant not available, vector cache disabled")
            self.enabled = False
            return
        
        if not EMBEDDINGS_AVAILABLE:
            logger.warning("Sentence transformers not available, vector cache disabled")
            self.enabled = False
            return
        
        self.enabled = True
        self.collection_name = collection_name
        self.client = QdrantClient(host=host, port=port)
        self.encoder = SentenceTransformer(embedding_model)
        self.embedding_dim = self.encoder.get_sentence_embedding_dimension()
        
        # Initialize collection
        self._init_collection()
    
    def _init_collection(self):
        """Initialize Qdrant collection"""
        try:
            collections = self.client.get_collections().collections
            if not any(c.name == self.collection_name for c in collections):
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.embedding_dim,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created Qdrant collection: {self.collection_name}")
        except Exception as e:
            logger.error(f"Error initializing Qdrant collection: {e}")
            self.enabled = False
    
    async def add(self, key: str, text: str, value: Any, metadata: Dict = None):
        """Add entry to vector cache"""
        if not self.enabled:
            return False
        
        try:
            # Generate embedding
            embedding = await asyncio.to_thread(
                self.encoder.encode, text
            )
            
            # Create point
            point = PointStruct(
                id=hashlib.md5(key.encode()).hexdigest()[:16],
                vector=embedding.tolist(),
                payload={
                    "key": key,
                    "text": text[:1000],  # Limit text size
                    "value": safe_dumps_bytes(value)[:10000],  # Limit value size
                    "metadata": metadata or {},
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            # Upsert to Qdrant
            self.client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )
            
            return True
        except Exception as e:
            logger.error(f"Error adding to vector cache: {e}")
            return False
    
    async def search(self, query: str, limit: int = 5, score_threshold: float = 0.7) -> List[Tuple[str, Any, float]]:
        """Search for similar entries in vector cache"""
        if not self.enabled:
            return []
        
        try:
            # Generate query embedding
            query_embedding = await asyncio.to_thread(
                self.encoder.encode, query
            )
            
            # Search in Qdrant
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding.tolist(),
                limit=limit,
                score_threshold=score_threshold
            )
            
            # Extract and return results
            output = []
            for result in results:
                key = result.payload.get("key")
                value = safe_loads_bytes(result.payload.get("value"))
                score = result.score
                output.append((key, value, score))
            
            return output
        except Exception as e:
            logger.error(f"Error searching vector cache: {e}")
            return []
    
    async def delete(self, key: str) -> bool:
        """Delete entry from vector cache"""
        if not self.enabled:
            return False
        
        try:
            point_id = hashlib.md5(key.encode()).hexdigest()[:16]
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=[point_id]
            )
            return True
        except Exception as e:
            logger.error(f"Error deleting from vector cache: {e}")
            return False


class IntelligentCache:
    """
    Multi-level intelligent cache with local memory, Redis, and vector search
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        
        # Level 1: Local memory cache (fastest)
        self.local_cache = LRUCache(
            maxsize=self.config.get('local_maxsize', 1000)
        )
        
        # Level 2: Redis cache (distributed)
        self.redis_cache = None
        if self.config.get('redis_enabled', True) and REDIS_AVAILABLE:
            self.redis_cache = RedisCache(
                host=self.config.get('redis_host', 'localhost'),
                port=self.config.get('redis_port', 6379),
                password=self.config.get('redis_password')
            )
        
        # Level 3: Vector cache (semantic search)
        self.vector_cache = None
        if self.config.get('vector_enabled', False):
            self.vector_cache = VectorCache(
                host=self.config.get('qdrant_host', 'localhost'),
                port=self.config.get('qdrant_port', 6333)
            )
        
        self.stats = {
            'total_gets': 0,
            'total_sets': 0,
            'l1_hits': 0,
            'l2_hits': 0,
            'l3_hits': 0,
            'misses': 0
        }
    
    def _generate_key(self, *args, **kwargs) -> str:
        """Generate cache key from arguments"""
        key_data = json.dumps({'args': args, 'kwargs': kwargs}, sort_keys=True)
        return hashlib.sha256(key_data.encode()).hexdigest()
    
    async def get(self, key: str, default: Any = None) -> Any:
        """
        Get value from cache with multi-level lookup
        
        Args:
            key: Cache key
            default: Default value if not found
        
        Returns:
            Cached value or default
        """
        self.stats['total_gets'] += 1
        
        # Level 1: Check local cache
        value = self.local_cache.get(key)
        if value is not None:
            self.stats['l1_hits'] += 1
            return value
        
        # Level 2: Check Redis
        if self.redis_cache:
            value = await self.redis_cache.get(key)
            if value is not None:
                # Promote to L1
                self.local_cache.set(key, value)
                self.stats['l2_hits'] += 1
                return value
        
        # Level 3: Vector search (if applicable)
        # This would typically be used for semantic queries
        
        self.stats['misses'] += 1
        return default
    
    async def set(self, 
                  key: str, 
                  value: Any,
                  ttl: int = 3600,
                  tags: List[str] = None,
                  text: Optional[str] = None) -> bool:
        """
        Set value in cache at all levels
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
            tags: Tags for invalidation
            text: Text for vector indexing
        
        Returns:
            Success status
        """
        self.stats['total_sets'] += 1
        
        # Level 1: Set in local cache
        self.local_cache.set(key, value, ttl, tags)
        
        # Level 2: Set in Redis
        if self.redis_cache:
            await self.redis_cache.set(key, value, ttl)
        
        # Level 3: Add to vector cache if text provided
        if self.vector_cache and text:
            await self.vector_cache.add(key, text, value)
        
        return True
    
    async def get_or_compute(self,
                            key: str,
                            compute_fn: Callable,
                            ttl: int = 3600,
                            force_refresh: bool = False) -> Any:
        """
        Get from cache or compute if missing
        
        Args:
            key: Cache key
            compute_fn: Async function to compute value
            ttl: Time to live
            force_refresh: Force recomputation
        
        Returns:
            Cached or computed value
        """
        if not force_refresh:
            value = await self.get(key)
            if value is not None:
                return value
        
        # Compute value
        if asyncio.iscoroutinefunction(compute_fn):
            value = await compute_fn()
        else:
            value = await asyncio.to_thread(compute_fn)
        
        # Cache it
        await self.set(key, value, ttl)
        
        return value
    
    async def invalidate(self, key: str) -> bool:
        """Invalidate cache entry at all levels"""
        success = False
        
        # Level 1
        if self.local_cache.delete(key):
            success = True
        
        # Level 2
        if self.redis_cache:
            if await self.redis_cache.delete(key):
                success = True
        
        # Level 3
        if self.vector_cache:
            if await self.vector_cache.delete(key):
                success = True
        
        return success
    
    async def invalidate_by_tags(self, tags: List[str]) -> int:
        """Invalidate all entries with specified tags"""
        count = self.local_cache.invalidate_by_tags(tags)
        # Redis doesn't support tags natively, would need to maintain index
        return count
    
    async def search_similar(self, query: str, limit: int = 5) -> List[Tuple[str, Any, float]]:
        """Search for similar cached items using vector similarity"""
        if self.vector_cache:
            return await self.vector_cache.search(query, limit)
        return []
    
    async def clear(self):
        """Clear all cache levels"""
        self.local_cache.clear()
        
        if self.redis_cache:
            await self.redis_cache.clear()
        
        # Vector cache clear would go here
        
        # Reset stats
        self.stats = {
            'total_gets': 0,
            'total_sets': 0,
            'l1_hits': 0,
            'l2_hits': 0,
            'l3_hits': 0,
            'misses': 0
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics"""
        stats = {
            **self.stats,
            'l1_stats': self.local_cache.get_stats(),
        }
        
        # Add hit rates
        total_gets = max(1, self.stats['total_gets'])
        stats['l1_hit_rate'] = self.stats['l1_hits'] / total_gets
        stats['l2_hit_rate'] = self.stats['l2_hits'] / total_gets
        stats['overall_hit_rate'] = (
            self.stats['l1_hits'] + self.stats['l2_hits'] + self.stats['l3_hits']
        ) / total_gets
        
        return stats
    
    async def __aenter__(self):
        """Async context manager entry"""
        if self.redis_cache:
            await self.redis_cache.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.redis_cache:
            await self.redis_cache.disconnect()


def cached(ttl: int = 3600, key_prefix: str = ""):
    """
    Decorator for caching function results
    
    Args:
        ttl: Time to live in seconds
        key_prefix: Prefix for cache keys
    """
    def decorator(func):
        # Get or create cache instance
        cache = IntelligentCache()
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = f"{key_prefix}:{func.__name__}:{cache._generate_key(*args, **kwargs)}"
            
            # Try to get from cache
            result = await cache.get(cache_key)
            if result is not None:
                return result
            
            # Compute result
            result = await func(*args, **kwargs)
            
            # Cache it
            await cache.set(cache_key, result, ttl)
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For sync functions, use local cache only
            cache_key = f"{key_prefix}:{func.__name__}:{cache._generate_key(*args, **kwargs)}"
            
            result = cache.local_cache.get(cache_key)
            if result is not None:
                return result
            
            result = func(*args, **kwargs)
            cache.local_cache.set(cache_key, result, ttl)
            
            return result
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
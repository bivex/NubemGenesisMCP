"""
Intelligent Cache System with Redis
Reduces latency and costs by caching appropriate responses
"""

import json
import hashlib
import time
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from enum import Enum
import redis
from core.safe_serialization import safe_dumps, safe_loads, safe_dumps_bytes, safe_loads_bytes
import logging

logger = logging.getLogger(__name__)

class CacheType(Enum):
    FACTUAL = "factual"          # Facts, definitions - cache 24h
    CODE = "code"                 # Code generation - cache 1h
    TRANSLATION = "translation"   # Translations - cache 7 days
    CREATIVE = "creative"         # Creative content - never cache
    ANALYSIS = "analysis"         # Analysis - cache 4h
    CONVERSATION = "conversation" # Conversations - cache 30 min
    SUMMARY = "summary"           # Summaries - cache 2h

class IntelligentCache:
    """
    Smart caching system that decides what to cache and for how long
    """
    
    def __init__(self, 
                 redis_host: str = "localhost", 
                 redis_port: int = 6379,
                 redis_db: int = 0,
                 max_cache_size_mb: int = 1024):
        
        try:
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                decode_responses=False  # We'll handle encoding
            )
            self.redis_client.ping()
            self.connected = True
            logger.info("Redis cache connected successfully")
        except Exception as e:
            logger.warning(f"Redis not available: {e}. Using in-memory cache.")
            self.redis_client = None
            self.connected = False
            self.memory_cache = {}  # Fallback to memory cache
        
        self.max_cache_size_mb = max_cache_size_mb
        
        # Cache TTL in seconds
        self.cache_ttl = {
            CacheType.FACTUAL: 86400,      # 24 hours
            CacheType.CODE: 3600,           # 1 hour
            CacheType.TRANSLATION: 604800,  # 7 days
            CacheType.CREATIVE: 0,          # Never cache
            CacheType.ANALYSIS: 14400,      # 4 hours
            CacheType.CONVERSATION: 1800,   # 30 minutes
            CacheType.SUMMARY: 7200,        # 2 hours
        }
        
        self.stats = {
            "hits": 0,
            "misses": 0,
            "saves": 0,
            "errors": 0
        }
    
    def _generate_cache_key(self, 
                          prompt: str, 
                          model: str = None,
                          context: Dict = None) -> str:
        """Generate a unique cache key for the request"""
        key_parts = [prompt]
        
        if model:
            key_parts.append(model)
        
        if context:
            # Sort context keys for consistent hashing
            sorted_context = json.dumps(context, sort_keys=True)
            key_parts.append(sorted_context)
        
        key_string = "|".join(key_parts)
        return f"nubem:cache:{hashlib.sha256(key_string.encode()).hexdigest()}"
    
    def _detect_cache_type(self, prompt: str, task_type: str = None) -> CacheType:
        """Intelligently detect what type of content this is"""
        
        if task_type:
            # Explicit type provided
            type_mapping = {
                "factual": CacheType.FACTUAL,
                "code": CacheType.CODE,
                "translation": CacheType.TRANSLATION,
                "creative": CacheType.CREATIVE,
                "analysis": CacheType.ANALYSIS,
                "conversation": CacheType.CONVERSATION,
                "summary": CacheType.SUMMARY
            }
            if task_type in type_mapping:
                return type_mapping[task_type]
        
        # Auto-detect based on prompt patterns
        prompt_lower = prompt.lower()
        
        # Creative content patterns
        creative_keywords = ["write a story", "create", "imagine", "poem", "creative", 
                           "generate a unique", "come up with", "invent"]
        if any(keyword in prompt_lower for keyword in creative_keywords):
            return CacheType.CREATIVE
        
        # Factual patterns
        factual_keywords = ["what is", "define", "explain", "who is", "when was", 
                          "where is", "fact about", "tell me about"]
        if any(keyword in prompt_lower for keyword in factual_keywords):
            return CacheType.FACTUAL
        
        # Code patterns
        code_keywords = ["code", "function", "implement", "algorithm", "debug", 
                        "fix", "program", "script", "class", "method"]
        if any(keyword in prompt_lower for keyword in code_keywords):
            return CacheType.CODE
        
        # Translation patterns
        if "translate" in prompt_lower or "translation" in prompt_lower:
            return CacheType.TRANSLATION
        
        # Summary patterns
        if "summarize" in prompt_lower or "summary" in prompt_lower:
            return CacheType.SUMMARY
        
        # Analysis patterns
        if "analyze" in prompt_lower or "analysis" in prompt_lower:
            return CacheType.ANALYSIS
        
        # Default to conversation with short TTL
        return CacheType.CONVERSATION
    
    def get(self, 
            prompt: str,
            model: str = None,
            context: Dict = None,
            task_type: str = None) -> Optional[Dict[str, Any]]:
        """
        Get cached response if available
        
        Returns:
            Cached response dict or None if not cached
        """
        cache_type = self._detect_cache_type(prompt, task_type)
        
        # Never return cache for creative content
        if cache_type == CacheType.CREATIVE:
            return None
        
        cache_key = self._generate_cache_key(prompt, model, context)
        
        try:
            if self.connected:
                cached_data = self.redis_client.get(cache_key)
                if cached_data:
                    self.stats["hits"] += 1
                    data = safe_loads_bytes(cached_data)
                    
                    # Add cache metadata
                    data["from_cache"] = True
                    data["cache_type"] = cache_type.value
                    data["cache_key"] = cache_key
                    
                    logger.debug(f"Cache HIT for {cache_type.value}: {cache_key[:20]}...")
                    return data
            else:
                # Fallback to memory cache
                if cache_key in self.memory_cache:
                    cached_item = self.memory_cache[cache_key]
                    if cached_item["expires"] > time.time():
                        self.stats["hits"] += 1
                        return cached_item["data"]
                    else:
                        # Expired, remove it
                        del self.memory_cache[cache_key]
            
            self.stats["misses"] += 1
            return None
            
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            self.stats["errors"] += 1
            return None
    
    def set(self,
            prompt: str,
            response: Dict[str, Any],
            model: str = None,
            context: Dict = None,
            task_type: str = None,
            force_ttl: int = None) -> bool:
        """
        Cache a response with intelligent TTL
        
        Returns:
            True if successfully cached
        """
        cache_type = self._detect_cache_type(prompt, task_type)
        
        # Never cache creative content
        if cache_type == CacheType.CREATIVE:
            logger.debug("Skipping cache for creative content")
            return False
        
        cache_key = self._generate_cache_key(prompt, model, context)
        ttl = force_ttl or self.cache_ttl[cache_type]
        
        # Add metadata to cached response
        cached_data = {
            **response,
            "cached_at": datetime.now().isoformat(),
            "cache_type": cache_type.value,
            "ttl": ttl,
            "model": model
        }
        
        try:
            if self.connected:
                serialized = safe_dumps_bytes(cached_data)
                
                # Check cache size before saving
                if len(serialized) > self.max_cache_size_mb * 1024 * 1024:
                    logger.warning(f"Response too large to cache: {len(serialized)} bytes")
                    return False
                
                self.redis_client.setex(
                    cache_key,
                    ttl,
                    serialized
                )
                self.stats["saves"] += 1
                logger.debug(f"Cached {cache_type.value} for {ttl}s: {cache_key[:20]}...")
                return True
            else:
                # Fallback to memory cache
                self.memory_cache[cache_key] = {
                    "data": cached_data,
                    "expires": time.time() + ttl
                }
                
                # Simple memory limit check
                if len(self.memory_cache) > 1000:
                    # Remove expired entries
                    current_time = time.time()
                    expired_keys = [k for k, v in self.memory_cache.items() 
                                  if v["expires"] < current_time]
                    for key in expired_keys:
                        del self.memory_cache[key]
                
                self.stats["saves"] += 1
                return True
                
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            self.stats["errors"] += 1
            return False
    
    def get_or_generate(self,
                       prompt: str,
                       generator_func,
                       model: str = None,
                       context: Dict = None,
                       task_type: str = None,
                       **generator_kwargs) -> Tuple[Dict[str, Any], bool]:
        """
        Get from cache or generate new response
        
        Args:
            prompt: The prompt to process
            generator_func: Function to call if not cached
            model: Model name for cache key
            context: Additional context for cache key
            task_type: Type of task for cache TTL
            **generator_kwargs: Arguments to pass to generator_func
            
        Returns:
            Tuple of (response, was_cached)
        """
        # Try to get from cache
        cached = self.get(prompt, model, context, task_type)
        if cached:
            return cached, True
        
        # Generate new response
        response = generator_func(prompt, **generator_kwargs)
        
        # Cache the response
        self.set(prompt, response, model, context, task_type)
        
        return response, False
    
    def invalidate(self, pattern: str = None):
        """Invalidate cache entries matching pattern"""
        if not self.connected:
            self.memory_cache.clear()
            return 0
        
        try:
            if pattern:
                keys = self.redis_client.keys(f"nubem:cache:{pattern}*")
            else:
                keys = self.redis_client.keys("nubem:cache:*")
            
            if keys:
                deleted = self.redis_client.delete(*keys)
                logger.info(f"Invalidated {deleted} cache entries")
                return deleted
            return 0
            
        except Exception as e:
            logger.error(f"Cache invalidation error: {e}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self.stats["hits"] + self.stats["misses"]
        hit_rate = (self.stats["hits"] / total_requests * 100) if total_requests > 0 else 0
        
        stats = {
            **self.stats,
            "hit_rate": f"{hit_rate:.1f}%",
            "total_requests": total_requests,
            "connected": self.connected
        }
        
        if self.connected:
            try:
                info = self.redis_client.info("memory")
                stats["redis_memory_used"] = info.get("used_memory_human", "N/A")
                stats["redis_memory_peak"] = info.get("used_memory_peak_human", "N/A")
            except:
                pass
        else:
            stats["memory_cache_size"] = len(self.memory_cache)
        
        return stats
    
    def optimize_cache(self) -> Dict[str, Any]:
        """Analyze cache usage and provide optimization suggestions"""
        stats = self.get_stats()
        suggestions = []
        
        if stats["hit_rate"].rstrip("%").replace(".", "") and float(stats["hit_rate"].rstrip("%")) < 30:
            suggestions.append({
                "priority": "HIGH",
                "suggestion": "Low hit rate - consider caching more content types",
                "action": "Review task_type detection logic"
            })
        
        if stats["errors"] > 10:
            suggestions.append({
                "priority": "CRITICAL",
                "suggestion": f"High error count ({stats['errors']})",
                "action": "Check Redis connection and memory limits"
            })
        
        if not self.connected:
            suggestions.append({
                "priority": "MEDIUM",
                "suggestion": "Using memory cache fallback",
                "action": "Ensure Redis is running: docker run -d -p 6379:6379 redis:alpine"
            })
        
        return {
            "stats": stats,
            "suggestions": suggestions,
            "cache_types": {ct.value: f"{ttl/3600:.1f}h" if ttl > 0 else "never" 
                          for ct, ttl in self.cache_ttl.items()}
        }


# Singleton instance
_cache_instance = None

def get_cache() -> IntelligentCache:
    """Get or create singleton cache instance"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = IntelligentCache()
    return _cache_instance


if __name__ == "__main__":
    # Test the intelligent cache
    cache = IntelligentCache()
    
    print("Testing Intelligent Cache\n" + "="*50)
    
    # Test cache type detection
    prompts = [
        ("What is the capital of France?", CacheType.FACTUAL),
        ("Write a creative story about dragons", CacheType.CREATIVE),
        ("Translate 'Hello' to Spanish", CacheType.TRANSLATION),
        ("Write a function to sort an array", CacheType.CODE),
        ("Summarize this article", CacheType.SUMMARY),
    ]
    
    for prompt, expected in prompts:
        detected = cache._detect_cache_type(prompt)
        print(f"Prompt: '{prompt[:30]}...'")
        print(f"  Expected: {expected.value}, Detected: {detected.value}")
        print(f"  TTL: {cache.cache_ttl[detected]/3600:.1f} hours\n")
    
    # Test caching
    test_response = {"result": "Paris", "confidence": 0.99}
    
    # Cache a factual response
    cache.set("What is the capital of France?", test_response, model="gpt-3.5-turbo")
    
    # Try to retrieve it
    cached = cache.get("What is the capital of France?", model="gpt-3.5-turbo")
    if cached:
        print(f"✅ Cache working! Retrieved: {cached}")
    
    # Show stats
    stats = cache.get_stats()
    print(f"\nCache Stats: {stats}")
    
    # Get optimization suggestions
    optimizations = cache.optimize_cache()
    print(f"\nOptimizations: {optimizations}")
"""
Request batching system for efficient API calls
Implements batching optimization from ChatGPT and Gemini
"""

import asyncio
from typing import List, Dict, Any, Callable, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import time
import logging
from uuid import uuid4

logger = logging.getLogger(__name__)

@dataclass
class BatchRequest:
    """Individual request in a batch"""
    id: str
    data: Any
    future: asyncio.Future
    timestamp: float
    metadata: Optional[Dict[str, Any]] = None

class RequestBatcher:
    """
    Intelligent request batching with:
    - Automatic batch formation
    - Size and time-based triggers
    - Request deduplication
    - Priority handling
    """
    
    def __init__(self,
                 batch_size: int = 10,
                 batch_timeout: float = 0.1,
                 max_batch_size: int = 100,
                 enable_deduplication: bool = True):
        
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.max_batch_size = max_batch_size
        self.enable_deduplication = enable_deduplication
        
        # Request storage
        self.pending_requests: Dict[str, List[BatchRequest]] = defaultdict(list)
        self.batch_tasks: Dict[str, asyncio.Task] = {}
        
        # Deduplication
        self.request_cache: Dict[str, Any] = {}
        self.dedup_futures: Dict[str, List[asyncio.Future]] = defaultdict(list)
        
        # Statistics
        self.stats = {
            'total_requests': 0,
            'batches_processed': 0,
            'duplicates_eliminated': 0,
            'avg_batch_size': 0.0,
            'avg_wait_time': 0.0
        }
        
        self._lock = asyncio.Lock()
    
    def _get_request_hash(self, data: Any) -> str:
        """Generate hash for request deduplication"""
        import hashlib
        import json
        
        if isinstance(data, dict):
            data_str = json.dumps(data, sort_keys=True)
        else:
            data_str = str(data)
        
        return hashlib.sha256(data_str.encode()).hexdigest()
    
    async def add_request(self,
                         key: str,
                         request_data: Any,
                         processor: Callable,
                         priority: int = 0,
                         metadata: Optional[Dict[str, Any]] = None) -> Any:
        """Add request to batch and wait for result"""
        
        request_id = str(uuid4())
        future = asyncio.Future()
        
        async with self._lock:
            self.stats['total_requests'] += 1
            
            # Check for deduplication
            if self.enable_deduplication:
                request_hash = self._get_request_hash(request_data)
                
                # Check if identical request is already pending
                if request_hash in self.dedup_futures:
                    self.dedup_futures[request_hash].append(future)
                    self.stats['duplicates_eliminated'] += 1
                    logger.debug(f"Request deduplicated: {request_hash[:8]}")
                    return await future
                
                # Check cache
                cache_key = f"{key}:{request_hash}"
                if cache_key in self.request_cache:
                    cached_result = self.request_cache[cache_key]
                    logger.debug(f"Request served from cache: {request_hash[:8]}")
                    return cached_result
                
                # Track for deduplication
                self.dedup_futures[request_hash] = [future]
            
            # Create batch request
            batch_request = BatchRequest(
                id=request_id,
                data=request_data,
                future=future,
                timestamp=time.time(),
                metadata=metadata
            )
            
            # Add to pending requests
            self.pending_requests[key].append(batch_request)
            
            # Sort by priority if needed
            if priority != 0:
                self.pending_requests[key].sort(
                    key=lambda r: r.metadata.get('priority', 0) if r.metadata else 0,
                    reverse=True
                )
            
            # Start batch processor if not running
            if key not in self.batch_tasks or self.batch_tasks[key].done():
                self.batch_tasks[key] = asyncio.create_task(
                    self._process_batch(key, processor)
                )
            
            # Check if batch is full
            if len(self.pending_requests[key]) >= self.batch_size:
                # Trigger immediate processing
                if key in self.batch_tasks:
                    self.batch_tasks[key].cancel()
                self.batch_tasks[key] = asyncio.create_task(
                    self._process_batch_immediate(key, processor)
                )
        
        # Wait for result
        return await future
    
    async def _process_batch(self, key: str, processor: Callable):
        """Process batch after timeout"""
        try:
            # Wait for timeout or batch to fill
            await asyncio.sleep(self.batch_timeout)
            
            async with self._lock:
                await self._execute_batch(key, processor)
                
        except asyncio.CancelledError:
            # Batch was triggered early (full batch)
            pass
        except Exception as e:
            logger.error(f"Batch processing error: {e}")
            # Set error for all pending requests
            async with self._lock:
                if key in self.pending_requests:
                    for request in self.pending_requests[key]:
                        if not request.future.done():
                            request.future.set_exception(e)
                    self.pending_requests[key].clear()
    
    async def _process_batch_immediate(self, key: str, processor: Callable):
        """Process batch immediately (when full)"""
        async with self._lock:
            await self._execute_batch(key, processor)
    
    async def _execute_batch(self, key: str, processor: Callable):
        """Execute the actual batch processing"""
        if key not in self.pending_requests or not self.pending_requests[key]:
            return
        
        # Get batch of requests
        batch_size = min(len(self.pending_requests[key]), self.max_batch_size)
        batch = self.pending_requests[key][:batch_size]
        self.pending_requests[key] = self.pending_requests[key][batch_size:]
        
        # Extract data for processing
        batch_data = [request.data for request in batch]
        
        # Update statistics
        self.stats['batches_processed'] += 1
        current_batch_size = len(batch)
        self.stats['avg_batch_size'] = (
            (self.stats['avg_batch_size'] * (self.stats['batches_processed'] - 1) + 
             current_batch_size) / self.stats['batches_processed']
        )
        
        # Calculate average wait time
        current_time = time.time()
        total_wait = sum(current_time - r.timestamp for r in batch)
        avg_wait = total_wait / len(batch)
        self.stats['avg_wait_time'] = (
            (self.stats['avg_wait_time'] * (self.stats['total_requests'] - len(batch)) + 
             total_wait) / self.stats['total_requests']
        )
        
        logger.debug(f"Processing batch of {len(batch)} requests for {key}")
        
        try:
            # Process batch
            if asyncio.iscoroutinefunction(processor):
                results = await processor(batch_data)
            else:
                results = processor(batch_data)
            
            # Ensure results match batch size
            if len(results) != len(batch):
                raise ValueError(f"Batch processor returned {len(results)} results for {len(batch)} requests")
            
            # Set results for each request
            for request, result in zip(batch, results):
                if not request.future.done():
                    request.future.set_result(result)
                
                # Cache result if deduplication enabled
                if self.enable_deduplication:
                    request_hash = self._get_request_hash(request.data)
                    cache_key = f"{key}:{request_hash}"
                    self.request_cache[cache_key] = result
                    
                    # Set result for deduplicated requests
                    if request_hash in self.dedup_futures:
                        for future in self.dedup_futures[request_hash]:
                            if not future.done():
                                future.set_result(result)
                        del self.dedup_futures[request_hash]
            
        except Exception as e:
            # Set exception for all requests in batch
            for request in batch:
                if not request.future.done():
                    request.future.set_exception(e)
            raise
    
    async def flush(self, key: Optional[str] = None):
        """Force process all pending batches"""
        async with self._lock:
            keys_to_flush = [key] if key else list(self.pending_requests.keys())
            
            for k in keys_to_flush:
                if k in self.batch_tasks:
                    self.batch_tasks[k].cancel()
                
                # Process remaining requests
                while self.pending_requests[k]:
                    processor = self.batch_tasks.get(k)
                    if processor:
                        await self._execute_batch(k, processor)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get batching statistics"""
        return {
            **self.stats,
            'pending_requests': sum(len(reqs) for reqs in self.pending_requests.values()),
            'cache_size': len(self.request_cache),
            'active_batches': len([t for t in self.batch_tasks.values() if not t.done()])
        }
    
    def clear_cache(self):
        """Clear the request cache"""
        self.request_cache.clear()
        logger.info("Request cache cleared")

class SmartBatcher:
    """
    Advanced batcher with adaptive batch sizing
    """
    
    def __init__(self):
        self.batchers: Dict[str, RequestBatcher] = {}
        self.performance_history: Dict[str, List[Tuple[int, float]]] = defaultdict(list)
    
    def get_or_create_batcher(self,
                             service: str,
                             batch_size: Optional[int] = None,
                             batch_timeout: Optional[float] = None) -> RequestBatcher:
        """Get or create batcher for service with adaptive sizing"""
        
        if service not in self.batchers:
            # Determine optimal batch size based on history
            if batch_size is None:
                batch_size = self._calculate_optimal_batch_size(service)
            
            if batch_timeout is None:
                batch_timeout = self._calculate_optimal_timeout(service)
            
            self.batchers[service] = RequestBatcher(
                batch_size=batch_size,
                batch_timeout=batch_timeout
            )
        
        return self.batchers[service]
    
    def _calculate_optimal_batch_size(self, service: str) -> int:
        """Calculate optimal batch size based on performance history"""
        if service not in self.performance_history:
            return 10  # Default
        
        history = self.performance_history[service]
        if len(history) < 10:
            return 10  # Not enough data
        
        # Find batch size with best throughput
        best_size = 10
        best_throughput = 0
        
        for size, latency in history[-100:]:  # Last 100 samples
            throughput = size / latency if latency > 0 else 0
            if throughput > best_throughput:
                best_throughput = throughput
                best_size = size
        
        return max(5, min(100, best_size))  # Clamp between 5 and 100
    
    def _calculate_optimal_timeout(self, service: str) -> float:
        """Calculate optimal timeout based on latency patterns"""
        if service not in self.performance_history:
            return 0.1  # Default 100ms
        
        history = self.performance_history[service]
        if len(history) < 10:
            return 0.1
        
        # Calculate average latency
        recent_latencies = [latency for _, latency in history[-50:]]
        avg_latency = sum(recent_latencies) / len(recent_latencies)
        
        # Set timeout to balance latency and batching efficiency
        return min(0.5, avg_latency * 0.1)  # 10% of average latency, max 500ms
    
    def record_performance(self, service: str, batch_size: int, latency: float):
        """Record performance metrics for adaptive optimization"""
        self.performance_history[service].append((batch_size, latency))
        
        # Keep only recent history
        if len(self.performance_history[service]) > 1000:
            self.performance_history[service] = self.performance_history[service][-500:]
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all batchers"""
        return {
            service: batcher.get_stats()
            for service, batcher in self.batchers.items()
        }

# Global smart batcher instance
global_smart_batcher = SmartBatcher()

def get_batcher(service: str) -> RequestBatcher:
    """Get batcher for specific service"""
    return global_smart_batcher.get_or_create_batcher(service)
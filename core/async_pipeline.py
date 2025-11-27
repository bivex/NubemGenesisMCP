"""
Asynchronous processing pipeline for improved concurrency
Implements async optimizations from Gemini and ChatGPT
"""

import asyncio
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4
import logging
from collections import defaultdict
from enum import Enum

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class Task:
    """Represents a task in the pipeline"""
    id: str
    name: str
    func: Callable
    args: tuple
    kwargs: dict
    status: TaskStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Any = None
    error: Optional[Exception] = None
    dependencies: List[str] = None
    priority: int = 0

class AsyncPipeline:
    """
    Advanced async processing pipeline with:
    - Task queuing and prioritization
    - Parallel execution
    - Dependency management
    - Result caching
    - Error handling and retries
    """
    
    def __init__(self,
                 max_workers: int = 10,
                 max_queue_size: int = 1000,
                 enable_result_cache: bool = True):
        
        self.max_workers = max_workers
        self.max_queue_size = max_queue_size
        self.enable_result_cache = enable_result_cache
        
        # Task management
        self.task_queue = asyncio.PriorityQueue(maxsize=max_queue_size)
        self.tasks: Dict[str, Task] = {}
        self.result_cache: Dict[str, Any] = {}
        
        # Workers
        self.workers: List[asyncio.Task] = []
        self.worker_semaphore = asyncio.Semaphore(max_workers)
        
        # Statistics
        self.stats = {
            'tasks_submitted': 0,
            'tasks_completed': 0,
            'tasks_failed': 0,
            'avg_execution_time': 0.0,
            'cache_hits': 0
        }
        
        # Running state
        self._running = False
        self._stop_event = asyncio.Event()
    
    async def start(self):
        """Start the pipeline workers"""
        if self._running:
            return
        
        self._running = True
        self._stop_event.clear()
        
        # Start worker tasks
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker(f"worker-{i}"))
            self.workers.append(worker)
        
        logger.info(f"Async pipeline started with {self.max_workers} workers")
    
    async def stop(self):
        """Stop the pipeline gracefully"""
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        
        # Wait for workers to complete
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()
        
        logger.info("Async pipeline stopped")
    
    async def submit(self,
                    func: Callable,
                    *args,
                    name: Optional[str] = None,
                    priority: int = 0,
                    dependencies: List[str] = None,
                    **kwargs) -> str:
        """Submit a task to the pipeline"""
        
        task_id = str(uuid4())
        task = Task(
            id=task_id,
            name=name or func.__name__,
            func=func,
            args=args,
            kwargs=kwargs,
            status=TaskStatus.PENDING,
            created_at=datetime.now(),
            dependencies=dependencies or [],
            priority=priority
        )
        
        # Store task
        self.tasks[task_id] = task
        self.stats['tasks_submitted'] += 1
        
        # Check cache if enabled
        if self.enable_result_cache:
            cache_key = self._get_cache_key(func, args, kwargs)
            if cache_key in self.result_cache:
                task.status = TaskStatus.COMPLETED
                task.result = self.result_cache[cache_key]
                self.stats['cache_hits'] += 1
                logger.debug(f"Task {task_id} served from cache")
                return task_id
        
        # Add to queue (priority queue uses negative priority for max heap)
        await self.task_queue.put((-priority, task_id, task))
        
        logger.debug(f"Task {task_id} submitted: {name}")
        return task_id
    
    async def _worker(self, worker_name: str):
        """Worker coroutine that processes tasks"""
        logger.debug(f"{worker_name} started")
        
        while not self._stop_event.is_set():
            try:
                # Get task from queue with timeout
                try:
                    priority, task_id, task = await asyncio.wait_for(
                        self.task_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Check dependencies
                if not await self._check_dependencies(task):
                    # Re-queue task if dependencies not met
                    await self.task_queue.put((priority, task_id, task))
                    await asyncio.sleep(0.1)
                    continue
                
                # Execute task
                async with self.worker_semaphore:
                    await self._execute_task(task)
                
            except Exception as e:
                logger.error(f"{worker_name} error: {e}")
        
        logger.debug(f"{worker_name} stopped")
    
    async def _check_dependencies(self, task: Task) -> bool:
        """Check if all task dependencies are completed"""
        for dep_id in task.dependencies:
            if dep_id not in self.tasks:
                return False
            
            dep_task = self.tasks[dep_id]
            if dep_task.status != TaskStatus.COMPLETED:
                return False
        
        return True
    
    async def _execute_task(self, task: Task):
        """Execute a single task"""
        try:
            # Update task status
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()
            
            logger.debug(f"Executing task {task.id}: {task.name}")
            
            # Execute function
            if asyncio.iscoroutinefunction(task.func):
                result = await task.func(*task.args, **task.kwargs)
            else:
                # Run sync function in executor
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    task.func,
                    *task.args
                )
            
            # Update task with result
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()
            task.result = result
            
            # Cache result if enabled
            if self.enable_result_cache:
                cache_key = self._get_cache_key(task.func, task.args, task.kwargs)
                self.result_cache[cache_key] = result
            
            # Update statistics
            execution_time = (task.completed_at - task.started_at).total_seconds()
            self.stats['tasks_completed'] += 1
            self.stats['avg_execution_time'] = (
                (self.stats['avg_execution_time'] * (self.stats['tasks_completed'] - 1) + 
                 execution_time) / self.stats['tasks_completed']
            )
            
            logger.debug(f"Task {task.id} completed in {execution_time:.2f}s")
            
        except Exception as e:
            # Handle task failure
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now()
            task.error = e
            
            self.stats['tasks_failed'] += 1
            
            logger.error(f"Task {task.id} failed: {e}")
    
    def _get_cache_key(self, func: Callable, args: tuple, kwargs: dict) -> str:
        """Generate cache key for function call"""
        import hashlib
        from core.safe_serialization import safe_dumps, safe_loads, safe_dumps_bytes, safe_loads_bytes
        
        key_data = (func.__name__, args, tuple(sorted(kwargs.items())))
        key_bytes = safe_dumps_bytes(key_data)
        return hashlib.sha256(key_bytes).hexdigest()
    
    async def get_result(self, task_id: str, timeout: Optional[float] = None) -> Any:
        """Get result of a task (wait if necessary)"""
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")
        
        task = self.tasks[task_id]
        
        # Wait for task completion
        start_time = asyncio.get_event_loop().time()
        while task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            if timeout and (asyncio.get_event_loop().time() - start_time) > timeout:
                raise asyncio.TimeoutError(f"Task {task_id} timeout")
            
            await asyncio.sleep(0.1)
        
        if task.status == TaskStatus.COMPLETED:
            return task.result
        elif task.status == TaskStatus.FAILED:
            raise task.error
        else:
            raise RuntimeError(f"Task {task_id} in unexpected state: {task.status}")
    
    async def batch_submit(self,
                          tasks: List[Tuple[Callable, tuple, dict]],
                          priority: int = 0) -> List[str]:
        """Submit multiple tasks in batch"""
        task_ids = []
        
        for func, args, kwargs in tasks:
            task_id = await self.submit(func, *args, priority=priority, **kwargs)
            task_ids.append(task_id)
        
        return task_ids
    
    async def map_async(self,
                       func: Callable,
                       items: List[Any],
                       priority: int = 0) -> List[Any]:
        """Map function over items asynchronously"""
        task_ids = []
        
        for item in items:
            task_id = await self.submit(func, item, priority=priority)
            task_ids.append(task_id)
        
        # Wait for all results
        results = []
        for task_id in task_ids:
            result = await self.get_result(task_id)
            results.append(result)
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pipeline statistics"""
        return {
            **self.stats,
            'queue_size': self.task_queue.qsize(),
            'active_workers': self.max_workers - self.worker_semaphore._value,
            'cache_size': len(self.result_cache)
        }
    
    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """Get status of a specific task"""
        if task_id in self.tasks:
            return self.tasks[task_id].status
        return None

# Global pipeline instance
global_pipeline = AsyncPipeline()

async def get_pipeline() -> AsyncPipeline:
    """Get the global pipeline instance"""
    if not global_pipeline._running:
        await global_pipeline.start()
    return global_pipeline
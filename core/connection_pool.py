#!/usr/bin/env python3
"""
Advanced Connection Pooling System for NubemSuperFClaude
Manages persistent connections with health checks and auto-recovery
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from contextlib import asynccontextmanager
import aiohttp

logger = logging.getLogger(__name__)

@dataclass
class PoolConfig:
    """Configuration for connection pools"""
    min_size: int = 5
    max_size: int = 20
    max_idle_time: int = 300
    health_check_interval: int = 30
    retry_attempts: int = 3
    connection_timeout: int = 10

@dataclass
class ConnectionStats:
    """Statistics for connection pool"""
    created: int = 0
    active: int = 0
    idle: int = 0
    failed: int = 0
    recycled: int = 0
    last_health_check: Optional[datetime] = None
    health_status: bool = True

class PersistentConnectionPool:
    """Advanced connection pooling with health checks"""
    
    def __init__(self, config: Optional[PoolConfig] = None):
        self.config = config or PoolConfig()
        self.pools: Dict[str, Any] = {}
        self.stats: Dict[str, ConnectionStats] = {}
        self._health_check_tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._initialized = False
        
    async def initialize(self):
        """Initialize all connection pools"""
        if self._initialized:
            return
            
        async with self._lock:
            if self._initialized:
                return
                
            logger.info("Initializing connection pools...")
            await self._init_http_pool()
            self._start_health_checks()
            self._initialized = True
            logger.info("Connection pools initialized successfully")
    
    async def _init_http_pool(self):
        """Initialize HTTP connection pool"""
        connector = aiohttp.TCPConnector(
            limit=self.config.max_size,
            limit_per_host=self.config.max_size // 4,
            ttl_dns_cache=300,
            enable_cleanup_closed=True
        )
        
        timeout = aiohttp.ClientTimeout(
            total=self.config.connection_timeout,
            connect=self.config.connection_timeout // 2
        )
        
        self.pools['http'] = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={'User-Agent': 'NubemSuperFClaude/2.0'}
        )
        
        self.stats['http'] = ConnectionStats()
        logger.info(f"HTTP pool initialized with max {self.config.max_size} connections")
    
    def _start_health_checks(self):
        """Start health check tasks for all pools"""
        for pool_name in self.pools:
            if self.pools[pool_name] is not None:
                task = asyncio.create_task(self._health_check_loop(pool_name))
                self._health_check_tasks[pool_name] = task
    
    async def _health_check_loop(self, pool_name: str):
        """Continuous health check for a pool"""
        while True:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                await self._check_pool_health(pool_name)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error for {pool_name}: {e}")
    
    async def _check_pool_health(self, pool_name: str):
        """Check health of a specific pool"""
        pool = self.pools.get(pool_name)
        if pool is None:
            return
        
        stats = self.stats[pool_name]
        stats.last_health_check = datetime.now()
        
        try:
            if pool_name == 'http':
                async with self.pools['http'].get('http://httpbin.org/status/200') as resp:
                    stats.health_status = resp.status == 200
        except Exception as e:
            logger.warning(f"Health check failed for {pool_name}: {e}")
            stats.health_status = False
            stats.failed += 1
    
    @asynccontextmanager
    async def get_http_client(self):
        """Get HTTP client from pool"""
        if not self._initialized:
            await self.initialize()
        
        client = self.pools.get('http')
        if client is None:
            raise ConnectionError("HTTP pool not available")
        
        self.stats['http'].active += 1
        try:
            yield client
        finally:
            self.stats['http'].active -= 1
            self.stats['http'].idle += 1
    
    def get_statistics(self) -> Dict[str, Dict[str, Any]]:
        """Get pool statistics"""
        stats = {}
        for pool_name, pool_stats in self.stats.items():
            stats[pool_name] = {
                'active': pool_stats.active,
                'idle': pool_stats.idle,
                'failed': pool_stats.failed,
                'recycled': pool_stats.recycled,
                'health_status': pool_stats.health_status,
                'last_health_check': pool_stats.last_health_check.isoformat() if pool_stats.last_health_check else None
            }
        return stats
    
    async def shutdown(self):
        """Shutdown all pools gracefully"""
        logger.info("Shutting down connection pools...")
        
        for task in self._health_check_tasks.values():
            task.cancel()
        
        await asyncio.gather(*self._health_check_tasks.values(), return_exceptions=True)
        
        for pool_name in list(self.pools.keys()):
            pool = self.pools.get(pool_name)
            if pool and pool_name == 'http':
                await pool.close()
        
        self._initialized = False
        logger.info("Connection pools shut down successfully")

# Global instance
_connection_pool: Optional[PersistentConnectionPool] = None

def get_connection_pool() -> PersistentConnectionPool:
    """Get or create global connection pool instance"""
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = PersistentConnectionPool()
    return _connection_pool
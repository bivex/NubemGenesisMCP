#!/usr/bin/env python3
"""
Qdrant Connection Pool Manager
Implementa connection pooling para operaciones eficientes con Qdrant
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
import time

logger = logging.getLogger(__name__)


@dataclass
class PoolConnection:
    """Wrapper para conexión con metadatos"""
    client: QdrantClient
    created_at: datetime
    last_used: datetime
    usage_count: int
    is_healthy: bool = True


@dataclass
class PoolStats:
    """Estadísticas del pool de conexiones"""
    total_connections: int
    active_connections: int
    idle_connections: int
    total_requests: int
    failed_requests: int
    avg_response_time_ms: float
    pool_hits: int
    pool_misses: int


class QdrantConnectionPool:
    """Pool de conexiones para Qdrant con health checking"""
    
    def __init__(self, 
                 host: str = "localhost",
                 port: int = 6333,
                 min_connections: int = 2,
                 max_connections: int = 10,
                 max_idle_time_minutes: int = 30,
                 health_check_interval_seconds: int = 60):
        
        self.host = host
        self.port = port
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.max_idle_time = timedelta(minutes=max_idle_time_minutes)
        self.health_check_interval = timedelta(seconds=health_check_interval_seconds)
        
        self._pool: List[PoolConnection] = []
        self._lock = asyncio.Lock()
        self._stats = PoolStats(0, 0, 0, 0, 0, 0.0, 0, 0)
        self._last_health_check = datetime.now()
        self._initialized = False
        
    async def initialize(self):
        """Inicializar el pool con conexiones mínimas"""
        if self._initialized:
            return
            
        async with self._lock:
            try:
                # Crear conexiones mínimas
                for _ in range(self.min_connections):
                    connection = await self._create_connection()
                    if connection:
                        self._pool.append(connection)
                        
                self._initialized = True
                logger.info(f"Qdrant connection pool initialized with {len(self._pool)} connections")
                
            except Exception as e:
                logger.error(f"Failed to initialize Qdrant pool: {e}")
                raise
    
    async def _create_connection(self) -> Optional[PoolConnection]:
        """Crear nueva conexión a Qdrant"""
        try:
            client = QdrantClient(host=self.host, port=self.port)
            
            # Test de conectividad
            await asyncio.to_thread(client.get_collections)
            
            return PoolConnection(
                client=client,
                created_at=datetime.now(),
                last_used=datetime.now(),
                usage_count=0,
                is_healthy=True
            )
            
        except Exception as e:
            logger.error(f"Failed to create Qdrant connection: {e}")
            return None
    
    async def _health_check_connection(self, connection: PoolConnection) -> bool:
        """Verificar salud de una conexión"""
        try:
            await asyncio.to_thread(connection.client.get_collections)
            connection.is_healthy = True
            return True
            
        except Exception as e:
            logger.warning(f"Health check failed for connection: {e}")
            connection.is_healthy = False
            return False
    
    async def _cleanup_idle_connections(self):
        """Remover conexiones inactivas"""
        if not self._initialized:
            return
            
        now = datetime.now()
        connections_to_remove = []
        
        for i, conn in enumerate(self._pool):
            if (now - conn.last_used > self.max_idle_time and 
                len(self._pool) > self.min_connections):
                connections_to_remove.append(i)
        
        # Remover de atrás hacia adelante para mantener índices
        for i in reversed(connections_to_remove):
            removed_conn = self._pool.pop(i)
            logger.debug(f"Removed idle connection (unused for {now - removed_conn.last_used})")
    
    async def _perform_health_checks(self):
        """Realizar health checks periódicos"""
        now = datetime.now()
        if now - self._last_health_check < self.health_check_interval:
            return
            
        healthy_connections = []
        
        for connection in self._pool:
            if await self._health_check_connection(connection):
                healthy_connections.append(connection)
            else:
                logger.warning("Removing unhealthy connection")
        
        self._pool = healthy_connections
        self._last_health_check = now
        
        # Asegurar conexiones mínimas
        while len(self._pool) < self.min_connections:
            new_conn = await self._create_connection()
            if new_conn:
                self._pool.append(new_conn)
            else:
                break
    
    @asynccontextmanager
    async def get_connection(self):
        """Context manager para obtener conexión del pool"""
        if not self._initialized:
            await self.initialize()
        
        connection = None
        start_time = time.time()
        
        try:
            async with self._lock:
                # Cleanup y health checks
                await self._cleanup_idle_connections()
                await self._perform_health_checks()
                
                # Buscar conexión disponible y saludable
                for conn in self._pool:
                    if conn.is_healthy:
                        connection = conn
                        self._stats.pool_hits += 1
                        break
                
                # Si no hay conexión disponible y podemos crear más
                if not connection and len(self._pool) < self.max_connections:
                    connection = await self._create_connection()
                    if connection:
                        self._pool.append(connection)
                        self._stats.pool_misses += 1
                
                # Si aún no hay conexión, usar la menos usada
                if not connection and self._pool:
                    connection = min(self._pool, key=lambda x: x.usage_count)
                    self._stats.pool_hits += 1
                
                if not connection:
                    raise Exception("No healthy connections available")
                
                # Actualizar estadísticas de conexión
                connection.last_used = datetime.now()
                connection.usage_count += 1
                
            # Actualizar estadísticas del pool
            self._stats.total_requests += 1
            
            yield connection.client
            
            # Registro exitoso
            response_time = (time.time() - start_time) * 1000
            self._update_response_time(response_time)
            
        except Exception as e:
            self._stats.failed_requests += 1
            logger.error(f"Error getting Qdrant connection: {e}")
            raise
            
    def _update_response_time(self, response_time_ms: float):
        """Actualizar tiempo promedio de respuesta"""
        if self._stats.total_requests == 1:
            self._stats.avg_response_time_ms = response_time_ms
        else:
            # Media móvil simple
            alpha = 0.1  # Factor de suavizado
            self._stats.avg_response_time_ms = (
                alpha * response_time_ms + 
                (1 - alpha) * self._stats.avg_response_time_ms
            )
    
    def get_stats(self) -> PoolStats:
        """Obtener estadísticas del pool"""
        active = len([c for c in self._pool if c.is_healthy])
        idle = len(self._pool) - active
        
        return PoolStats(
            total_connections=len(self._pool),
            active_connections=active,
            idle_connections=idle,
            total_requests=self._stats.total_requests,
            failed_requests=self._stats.failed_requests,
            avg_response_time_ms=round(self._stats.avg_response_time_ms, 2),
            pool_hits=self._stats.pool_hits,
            pool_misses=self._stats.pool_misses
        )
    
    async def close(self):
        """Cerrar todas las conexiones del pool"""
        async with self._lock:
            for connection in self._pool:
                try:
                    connection.client.close()
                except:
                    pass
            
            self._pool.clear()
            self._initialized = False
            logger.info("Qdrant connection pool closed")


# Singleton global del pool
_qdrant_pool: Optional[QdrantConnectionPool] = None


async def get_qdrant_pool(host: str = "localhost", 
                         port: int = 6333,
                         **kwargs) -> QdrantConnectionPool:
    """Obtener instancia singleton del pool de Qdrant"""
    global _qdrant_pool
    
    if _qdrant_pool is None:
        _qdrant_pool = QdrantConnectionPool(host=host, port=port, **kwargs)
        await _qdrant_pool.initialize()
    
    return _qdrant_pool


async def close_qdrant_pool():
    """Cerrar el pool global de Qdrant"""
    global _qdrant_pool
    
    if _qdrant_pool:
        await _qdrant_pool.close()
        _qdrant_pool = None
#!/usr/bin/env python3
"""
Advanced Health Check System for NubemSuperFClaude
Proporciona health checks granulares para todos los componentes del sistema
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Estados de salud de componentes"""
    HEALTHY = "healthy"
    DEGRADED = "degraded" 
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Resultado de un health check individual"""
    component: str
    status: HealthStatus
    response_time_ms: float
    message: str = ""
    details: Dict[str, Any] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.details is None:
            self.details = {}


@dataclass
class SystemHealthReport:
    """Reporte completo de salud del sistema"""
    overall_status: HealthStatus
    components: Dict[str, HealthCheckResult]
    total_checks: int
    healthy_checks: int
    degraded_checks: int
    unhealthy_checks: int
    total_response_time_ms: float
    timestamp: datetime
    
    @property
    def health_percentage(self) -> float:
        """Porcentaje de componentes saludables"""
        if self.total_checks == 0:
            return 0.0
        return (self.healthy_checks / self.total_checks) * 100


class HealthChecker:
    """Sistema de health checks avanzado"""
    
    def __init__(self):
        self.checks: Dict[str, Callable] = {}
        self.check_history: List[SystemHealthReport] = []
        self.max_history = 50
        self._last_check_time = {}
        self._check_intervals = {}  # component -> interval_seconds
    
    def register_check(self, 
                      component: str, 
                      check_func: Callable, 
                      interval_seconds: int = 30):
        """Registrar un health check para un componente"""
        self.checks[component] = check_func
        self._check_intervals[component] = interval_seconds
        logger.info(f"Registered health check for {component}")
    
    async def run_check(self, component: str) -> HealthCheckResult:
        """Ejecutar health check para un componente específico"""
        if component not in self.checks:
            return HealthCheckResult(
                component=component,
                status=HealthStatus.UNKNOWN,
                response_time_ms=0,
                message=f"No health check registered for {component}"
            )
        
        start_time = time.time()
        
        try:
            check_func = self.checks[component]
            
            # Execute check with timeout
            result = await asyncio.wait_for(
                check_func(), timeout=10.0
            )
            
            response_time = (time.time() - start_time) * 1000
            
            if isinstance(result, HealthCheckResult):
                result.response_time_ms = response_time
                return result
            elif isinstance(result, bool):
                return HealthCheckResult(
                    component=component,
                    status=HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY,
                    response_time_ms=response_time,
                    message="OK" if result else "Check failed"
                )
            else:
                return HealthCheckResult(
                    component=component,
                    status=HealthStatus.HEALTHY,
                    response_time_ms=response_time,
                    message=str(result) if result else "OK",
                    details=result if isinstance(result, dict) else {}
                )
                
        except asyncio.TimeoutError:
            response_time = (time.time() - start_time) * 1000
            return HealthCheckResult(
                component=component,
                status=HealthStatus.UNHEALTHY,
                response_time_ms=response_time,
                message="Health check timed out"
            )
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            logger.error(f"Health check failed for {component}: {e}")
            return HealthCheckResult(
                component=component,
                status=HealthStatus.UNHEALTHY,
                response_time_ms=response_time,
                message=f"Check failed: {str(e)}"
            )
    
    async def run_all_checks(self, force: bool = False) -> SystemHealthReport:
        """Ejecutar todos los health checks registrados"""
        now = datetime.now()
        checks_to_run = []
        
        for component in self.checks.keys():
            # Check if we should run this check based on interval
            last_check = self._last_check_time.get(component, datetime.min)
            interval = self._check_intervals.get(component, 30)
            
            if force or (now - last_check).total_seconds() >= interval:
                checks_to_run.append(component)
                self._last_check_time[component] = now
        
        if not checks_to_run:
            # Return last known status if no checks needed
            if self.check_history:
                return self.check_history[-1]
        
        # Run checks concurrently
        start_time = time.time()
        
        if checks_to_run:
            tasks = [self.run_check(component) for component in checks_to_run]
            check_results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            check_results = []
        
        total_time = (time.time() - start_time) * 1000
        
        # Process results
        components = {}
        healthy_count = 0
        degraded_count = 0
        unhealthy_count = 0
        
        # Include previous results for components not checked this time
        if self.check_history and not force:
            last_report = self.check_history[-1]
            components.update(last_report.components)
        
        # Update with new results
        for i, component in enumerate(checks_to_run):
            if i < len(check_results):
                result = check_results[i]
                if isinstance(result, Exception):
                    result = HealthCheckResult(
                        component=component,
                        status=HealthStatus.UNHEALTHY,
                        response_time_ms=0,
                        message=f"Check failed: {str(result)}"
                    )
                components[component] = result
        
        # Count statuses
        for result in components.values():
            if result.status == HealthStatus.HEALTHY:
                healthy_count += 1
            elif result.status == HealthStatus.DEGRADED:
                degraded_count += 1
            elif result.status == HealthStatus.UNHEALTHY:
                unhealthy_count += 1
        
        # Determine overall status
        total_checks = len(components)
        if unhealthy_count > 0:
            overall_status = HealthStatus.UNHEALTHY
        elif degraded_count > 0:
            overall_status = HealthStatus.DEGRADED
        elif healthy_count > 0:
            overall_status = HealthStatus.HEALTHY
        else:
            overall_status = HealthStatus.UNKNOWN
        
        # Create report
        report = SystemHealthReport(
            overall_status=overall_status,
            components=components,
            total_checks=total_checks,
            healthy_checks=healthy_count,
            degraded_checks=degraded_count,
            unhealthy_checks=unhealthy_count,
            total_response_time_ms=total_time,
            timestamp=now
        )
        
        # Store in history
        self.check_history.append(report)
        if len(self.check_history) > self.max_history:
            self.check_history.pop(0)
        
        return report
    
    def get_component_history(self, component: str, 
                            hours: int = 24) -> List[HealthCheckResult]:
        """Obtener historial de un componente específico"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        history = []
        
        for report in self.check_history:
            if report.timestamp >= cutoff_time:
                if component in report.components:
                    history.append(report.components[component])
        
        return history
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Obtener estadísticas del sistema de health checks"""
        if not self.check_history:
            return {"message": "No health check history available"}
        
        recent_reports = self.check_history[-10:]  # Last 10 reports
        
        avg_response_time = sum(r.total_response_time_ms for r in recent_reports) / len(recent_reports)
        avg_health_percentage = sum(r.health_percentage for r in recent_reports) / len(recent_reports)
        
        uptime_samples = [r.overall_status == HealthStatus.HEALTHY for r in recent_reports]
        uptime_percentage = (sum(uptime_samples) / len(uptime_samples)) * 100
        
        return {
            "total_components": len(self.checks),
            "avg_response_time_ms": round(avg_response_time, 2),
            "avg_health_percentage": round(avg_health_percentage, 2),
            "uptime_percentage": round(uptime_percentage, 2),
            "total_reports": len(self.check_history),
            "last_check": self.check_history[-1].timestamp.isoformat() if self.check_history else None
        }


# Default health checks for common components

async def check_redis_health() -> HealthCheckResult:
    """Health check para Redis"""
    try:
        import redis.asyncio as redis
        import os
        
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        client = redis.from_url(redis_url)
        
        start_time = time.time()
        await client.ping()
        response_time = (time.time() - start_time) * 1000
        
        info = await client.info()
        await client.close()
        
        return HealthCheckResult(
            component="redis",
            status=HealthStatus.HEALTHY,
            response_time_ms=response_time,
            message="Redis is responsive",
            details={
                "version": info.get("redis_version", "unknown"),
                "used_memory_mb": round(info.get("used_memory", 0) / 1024 / 1024, 2),
                "connected_clients": info.get("connected_clients", 0)
            }
        )
        
    except Exception as e:
        return HealthCheckResult(
            component="redis",
            status=HealthStatus.UNHEALTHY,
            response_time_ms=0,
            message=f"Redis check failed: {str(e)}"
        )


async def check_qdrant_health() -> HealthCheckResult:
    """Health check para Qdrant"""
    try:
        from .qdrant_connection_pool import get_qdrant_pool
        
        start_time = time.time()
        pool = await get_qdrant_pool()
        
        async with pool.get_connection() as client:
            collections = await asyncio.to_thread(client.get_collections)
            response_time = (time.time() - start_time) * 1000
            
            pool_stats = pool.get_stats()
            
            return HealthCheckResult(
                component="qdrant",
                status=HealthStatus.HEALTHY,
                response_time_ms=response_time,
                message="Qdrant is responsive",
                details={
                    "collections_count": len(collections.collections),
                    "pool_connections": pool_stats.total_connections,
                    "pool_requests": pool_stats.total_requests,
                    "avg_pool_response_ms": pool_stats.avg_response_time_ms
                }
            )
            
    except Exception as e:
        return HealthCheckResult(
            component="qdrant",
            status=HealthStatus.UNHEALTHY,
            response_time_ms=0,
            message=f"Qdrant check failed: {str(e)}"
        )


async def check_cache_health() -> HealthCheckResult:
    """Health check para el sistema de cache"""
    try:
        from .cache_manager import get_cache_manager
        
        start_time = time.time()
        cache_manager = get_cache_manager()
        
        # Test cache operations
        test_key = "health_check_test"
        test_value = {"timestamp": time.time()}
        
        await cache_manager.set(test_key, test_value)
        retrieved_value = await cache_manager.get(test_key)
        await cache_manager.delete(test_key)
        
        response_time = (time.time() - start_time) * 1000
        
        stats = cache_manager.get_stats()
        
        status = HealthStatus.HEALTHY
        if stats.get('memory_usage_pct', 0) > 90:
            status = HealthStatus.DEGRADED
        
        return HealthCheckResult(
            component="cache",
            status=status,
            response_time_ms=response_time,
            message="Cache is operational",
            details=stats
        )
        
    except Exception as e:
        return HealthCheckResult(
            component="cache",
            status=HealthStatus.UNHEALTHY,
            response_time_ms=0,
            message=f"Cache check failed: {str(e)}"
        )


# Singleton health checker
_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Obtener instancia singleton del health checker"""
    global _health_checker
    
    if _health_checker is None:
        _health_checker = HealthChecker()
        
        # Register default checks
        _health_checker.register_check("redis", check_redis_health, 30)
        _health_checker.register_check("qdrant", check_qdrant_health, 60)
        _health_checker.register_check("cache", check_cache_health, 45)
        
    return _health_checker
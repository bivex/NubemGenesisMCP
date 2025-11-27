#!/usr/bin/env python3
"""
Personas Metrics System for NubemSuperFClaude
Sistema de métricas avanzado para el uso de personas IA
"""

import time
import logging
from typing import Dict, Any, List, Optional, Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, deque
import asyncio
import json

logger = logging.getLogger(__name__)


@dataclass
class PersonaUsageStats:
    """Estadísticas de uso de una persona"""
    persona_id: str
    total_invocations: int = 0
    total_tokens: int = 0
    total_response_time_ms: float = 0
    avg_response_time_ms: float = 0
    success_rate: float = 100.0
    last_used: Optional[datetime] = None
    error_count: int = 0
    categories_used: List[str] = field(default_factory=list)
    popular_tasks: Counter = field(default_factory=Counter)


@dataclass
class PersonaInteraction:
    """Registro de una interacción con persona"""
    persona_id: str
    timestamp: datetime
    task_type: str
    response_time_ms: float
    tokens_used: int = 0
    success: bool = True
    error_message: Optional[str] = None
    context_category: Optional[str] = None


@dataclass
class OrchestrationMetrics:
    """Métricas del sistema de orquestación"""
    total_orchestrations: int = 0
    avg_personas_per_task: float = 0
    successful_orchestrations: int = 0
    failed_orchestrations: int = 0
    avg_orchestration_time_ms: float = 0
    most_requested_categories: Counter = field(default_factory=Counter)
    collaboration_patterns: Dict[str, int] = field(default_factory=dict)


class PersonasMetricsCollector:
    """Colector de métricas para el sistema de personas"""
    
    def __init__(self, max_history_size: int = 10000):
        self.max_history_size = max_history_size
        self.personas_stats: Dict[str, PersonaUsageStats] = {}
        self.interaction_history: deque = deque(maxlen=max_history_size)
        self.orchestration_metrics = OrchestrationMetrics()
        
        # Real-time metrics
        self.hourly_usage: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
        self.category_performance: Dict[str, List[float]] = defaultdict(list)
        
        # Caches para performance
        self._cached_reports = {}
        self._cache_expiry = {}
        self._cache_duration = 300  # 5 minutes
        
        self._start_time = datetime.now()
        
    def record_interaction(self, 
                          persona_id: str,
                          task_type: str,
                          response_time_ms: float,
                          tokens_used: int = 0,
                          success: bool = True,
                          error_message: Optional[str] = None,
                          context_category: Optional[str] = None):
        """Registrar una interacción con una persona"""
        
        interaction = PersonaInteraction(
            persona_id=persona_id,
            timestamp=datetime.now(),
            task_type=task_type,
            response_time_ms=response_time_ms,
            tokens_used=tokens_used,
            success=success,
            error_message=error_message,
            context_category=context_category
        )
        
        # Add to history
        self.interaction_history.append(interaction)
        
        # Update persona stats
        if persona_id not in self.personas_stats:
            self.personas_stats[persona_id] = PersonaUsageStats(persona_id=persona_id)
        
        stats = self.personas_stats[persona_id]
        stats.total_invocations += 1
        stats.total_tokens += tokens_used
        stats.total_response_time_ms += response_time_ms
        stats.avg_response_time_ms = stats.total_response_time_ms / stats.total_invocations
        stats.last_used = interaction.timestamp
        
        if not success:
            stats.error_count += 1
        
        stats.success_rate = ((stats.total_invocations - stats.error_count) / 
                             stats.total_invocations * 100)
        
        # Update task popularity
        stats.popular_tasks[task_type] += 1
        
        # Update category usage
        if context_category and context_category not in stats.categories_used:
            stats.categories_used.append(context_category)
        
        # Update hourly usage
        current_hour = interaction.timestamp.hour
        today_key = interaction.timestamp.strftime("%Y-%m-%d")
        self.hourly_usage[today_key][current_hour] += 1
        
        # Update category performance
        if context_category:
            self.category_performance[context_category].append(response_time_ms)
            # Keep only last 100 measurements per category
            if len(self.category_performance[context_category]) > 100:
                self.category_performance[context_category].pop(0)
        
        # Clear relevant caches
        self._invalidate_cache(['usage_report', 'performance_report'])
        
    def record_orchestration(self,
                           personas_used: List[str],
                           orchestration_time_ms: float,
                           success: bool = True,
                           categories_involved: Optional[List[str]] = None):
        """Registrar una orquestación de personas"""
        
        self.orchestration_metrics.total_orchestrations += 1
        
        if success:
            self.orchestration_metrics.successful_orchestrations += 1
        else:
            self.orchestration_metrics.failed_orchestrations += 1
        
        # Update average
        total_time = (self.orchestration_metrics.avg_orchestration_time_ms * 
                     (self.orchestration_metrics.total_orchestrations - 1) + 
                     orchestration_time_ms)
        self.orchestration_metrics.avg_orchestration_time_ms = (
            total_time / self.orchestration_metrics.total_orchestrations
        )
        
        # Update personas per task average
        total_personas = (self.orchestration_metrics.avg_personas_per_task * 
                         (self.orchestration_metrics.total_orchestrations - 1) + 
                         len(personas_used))
        self.orchestration_metrics.avg_personas_per_task = (
            total_personas / self.orchestration_metrics.total_orchestrations
        )
        
        # Update category requests
        if categories_involved:
            for category in categories_involved:
                self.orchestration_metrics.most_requested_categories[category] += 1
        
        # Track collaboration patterns
        if len(personas_used) > 1:
            pattern = " + ".join(sorted(personas_used))
            self.orchestration_metrics.collaboration_patterns[pattern] = (
                self.orchestration_metrics.collaboration_patterns.get(pattern, 0) + 1
            )
        
        self._invalidate_cache(['orchestration_report'])
    
    def _invalidate_cache(self, keys: List[str]):
        """Invalidar caches específicos"""
        for key in keys:
            if key in self._cached_reports:
                del self._cached_reports[key]
                del self._cache_expiry[key]
    
    def _get_cached_or_generate(self, cache_key: str, generator_func):
        """Obtener de cache o generar nuevo reporte"""
        now = datetime.now()
        
        # Check if cache is valid
        if (cache_key in self._cached_reports and 
            cache_key in self._cache_expiry and
            now < self._cache_expiry[cache_key]):
            return self._cached_reports[cache_key]
        
        # Generate new report
        report = generator_func()
        
        # Cache it
        self._cached_reports[cache_key] = report
        self._cache_expiry[cache_key] = now + timedelta(seconds=self._cache_duration)
        
        return report
    
    def get_persona_usage_report(self) -> Dict[str, Any]:
        """Generar reporte de uso de personas"""
        
        def generate_report():
            if not self.personas_stats:
                return {"message": "No persona usage data available"}
            
            # Top personas by usage
            top_personas = sorted(
                self.personas_stats.values(),
                key=lambda x: x.total_invocations,
                reverse=True
            )[:10]
            
            # Category distribution
            category_usage = defaultdict(int)
            for stats in self.personas_stats.values():
                for category in stats.categories_used:
                    category_usage[category] += stats.total_invocations
            
            # Performance metrics
            avg_response_times = {
                persona_id: stats.avg_response_time_ms
                for persona_id, stats in self.personas_stats.items()
            }
            
            fastest_personas = sorted(avg_response_times.items(), key=lambda x: x[1])[:5]
            
            total_invocations = sum(stats.total_invocations for stats in self.personas_stats.values())
            total_tokens = sum(stats.total_tokens for stats in self.personas_stats.values())
            
            return {
                "summary": {
                    "total_personas_used": len(self.personas_stats),
                    "total_invocations": total_invocations,
                    "total_tokens_processed": total_tokens,
                    "avg_tokens_per_invocation": total_tokens / total_invocations if total_invocations > 0 else 0
                },
                "top_personas": [
                    {
                        "persona_id": stats.persona_id,
                        "invocations": stats.total_invocations,
                        "success_rate": round(stats.success_rate, 2),
                        "avg_response_time_ms": round(stats.avg_response_time_ms, 2),
                        "last_used": stats.last_used.isoformat() if stats.last_used else None
                    }
                    for stats in top_personas
                ],
                "category_distribution": dict(category_usage),
                "performance": {
                    "fastest_personas": [
                        {"persona_id": pid, "avg_response_time_ms": round(time_ms, 2)}
                        for pid, time_ms in fastest_personas
                    ],
                    "overall_avg_response_time_ms": round(
                        sum(stats.avg_response_time_ms * stats.total_invocations 
                            for stats in self.personas_stats.values()) / total_invocations
                        if total_invocations > 0 else 0, 2
                    )
                },
                "timestamp": datetime.now().isoformat()
            }
        
        return self._get_cached_or_generate('usage_report', generate_report)
    
    def get_orchestration_report(self) -> Dict[str, Any]:
        """Generar reporte de orquestación"""
        
        def generate_report():
            metrics = self.orchestration_metrics
            
            if metrics.total_orchestrations == 0:
                return {"message": "No orchestration data available"}
            
            success_rate = (metrics.successful_orchestrations / 
                          metrics.total_orchestrations * 100)
            
            # Top collaboration patterns
            top_patterns = sorted(
                metrics.collaboration_patterns.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]
            
            return {
                "summary": {
                    "total_orchestrations": metrics.total_orchestrations,
                    "success_rate": round(success_rate, 2),
                    "avg_personas_per_task": round(metrics.avg_personas_per_task, 2),
                    "avg_orchestration_time_ms": round(metrics.avg_orchestration_time_ms, 2)
                },
                "category_requests": dict(metrics.most_requested_categories.most_common(10)),
                "collaboration_patterns": [
                    {"pattern": pattern, "count": count}
                    for pattern, count in top_patterns
                ],
                "timestamp": datetime.now().isoformat()
            }
        
        return self._get_cached_or_generate('orchestration_report', generate_report)
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Generar reporte de rendimiento"""
        
        def generate_report():
            if not self.category_performance:
                return {"message": "No performance data available"}
            
            category_stats = {}
            for category, times in self.category_performance.items():
                if times:
                    category_stats[category] = {
                        "avg_response_time_ms": round(sum(times) / len(times), 2),
                        "min_response_time_ms": round(min(times), 2),
                        "max_response_time_ms": round(max(times), 2),
                        "sample_count": len(times)
                    }
            
            # Recent activity (last 24 hours)
            now = datetime.now()
            recent_interactions = [
                interaction for interaction in self.interaction_history
                if (now - interaction.timestamp) <= timedelta(hours=24)
            ]
            
            hourly_activity = defaultdict(int)
            for interaction in recent_interactions:
                hour_key = interaction.timestamp.strftime("%H:00")
                hourly_activity[hour_key] += 1
            
            return {
                "category_performance": category_stats,
                "recent_activity_24h": {
                    "total_interactions": len(recent_interactions),
                    "hourly_distribution": dict(hourly_activity),
                    "success_rate": round(
                        sum(1 for i in recent_interactions if i.success) / 
                        len(recent_interactions) * 100
                        if recent_interactions else 100, 2
                    )
                },
                "system_uptime_hours": round(
                    (datetime.now() - self._start_time).total_seconds() / 3600, 2
                ),
                "timestamp": datetime.now().isoformat()
            }
        
        return self._get_cached_or_generate('performance_report', generate_report)
    
    def get_comprehensive_report(self) -> Dict[str, Any]:
        """Generar reporte comprehensivo"""
        return {
            "usage": self.get_persona_usage_report(),
            "orchestration": self.get_orchestration_report(),
            "performance": self.get_performance_report()
        }
    
    def get_persona_details(self, persona_id: str) -> Optional[Dict[str, Any]]:
        """Obtener detalles específicos de una persona"""
        if persona_id not in self.personas_stats:
            return None
        
        stats = self.personas_stats[persona_id]
        
        # Get recent interactions for this persona
        recent_interactions = [
            interaction for interaction in self.interaction_history
            if (interaction.persona_id == persona_id and
                (datetime.now() - interaction.timestamp) <= timedelta(hours=24))
        ]
        
        return {
            "persona_id": persona_id,
            "statistics": {
                "total_invocations": stats.total_invocations,
                "total_tokens": stats.total_tokens,
                "avg_response_time_ms": round(stats.avg_response_time_ms, 2),
                "success_rate": round(stats.success_rate, 2),
                "error_count": stats.error_count,
                "last_used": stats.last_used.isoformat() if stats.last_used else None
            },
            "usage_patterns": {
                "categories_used": stats.categories_used,
                "popular_tasks": dict(stats.popular_tasks.most_common(10))
            },
            "recent_activity_24h": {
                "interactions_count": len(recent_interactions),
                "avg_response_time_ms": round(
                    sum(i.response_time_ms for i in recent_interactions) / 
                    len(recent_interactions)
                    if recent_interactions else 0, 2
                ),
                "success_rate": round(
                    sum(1 for i in recent_interactions if i.success) /
                    len(recent_interactions) * 100
                    if recent_interactions else 100, 2
                )
            }
        }


# Singleton metrics collector
_metrics_collector: Optional[PersonasMetricsCollector] = None


def get_personas_metrics() -> PersonasMetricsCollector:
    """Obtener instancia singleton del colector de métricas"""
    global _metrics_collector
    
    if _metrics_collector is None:
        _metrics_collector = PersonasMetricsCollector()
    
    return _metrics_collector
"""
MCP Health Monitor - Comprehensive health tracking

Provides:
- Real-time health monitoring of all MCPs
- Performance metrics tracking
- Auto-disable unhealthy MCPs
- Health reports and alerts
"""

import logging
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import statistics

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthMetrics:
    """Health metrics for an MCP"""
    mcp_name: str
    status: HealthStatus
    response_time_ms: float
    error_rate_percent: float
    success_rate_percent: float
    last_check_time: float
    uptime_percent: float
    consecutive_failures: int
    is_loaded: bool
    is_enabled: bool


@dataclass
class HealthCheckConfig:
    """Configuration for health checks"""
    check_interval_seconds: int = 60
    response_time_threshold_ms: int = 1000
    error_rate_threshold_percent: float = 10.0
    min_calls_for_stats: int = 10
    auto_disable_unhealthy: bool = True
    consecutive_failures_threshold: int = 3


class MCPHealthMonitor:
    """
    Health monitor for all MCPs

    Responsibilities:
    - Periodic health checks
    - Performance tracking
    - Auto-disable unhealthy MCPs
    - Generate health reports
    """

    def __init__(self, registry, config: Optional[HealthCheckConfig] = None):
        """
        Initialize health monitor

        Args:
            registry: MCPRegistry instance
            config: Health check configuration
        """
        self.registry = registry
        self.config = config or HealthCheckConfig()

        self._last_check_time: Optional[float] = None
        self._health_history: Dict[str, List[HealthMetrics]] = {}
        self._alerts: List[Dict[str, Any]] = []

        logger.info("MCPHealthMonitor initialized")

    def check_health(self, mcp_name: str) -> HealthMetrics:
        """
        Check health of a single MCP

        Args:
            mcp_name: MCP name

        Returns:
            HealthMetrics for the MCP
        """
        instance = self.registry.get(mcp_name, auto_load=False)

        if instance is None:
            return HealthMetrics(
                mcp_name=mcp_name,
                status=HealthStatus.UNKNOWN,
                response_time_ms=0,
                error_rate_percent=0,
                success_rate_percent=0,
                last_check_time=time.time(),
                uptime_percent=0,
                consecutive_failures=0,
                is_loaded=False,
                is_enabled=False,
            )

        # Calculate metrics
        total_calls = instance.total_calls
        error_rate = 0.0
        success_rate = 0.0

        if total_calls >= self.config.min_calls_for_stats:
            error_rate = (instance.error_count / total_calls) * 100
            success_rate = (instance.success_count / total_calls) * 100
        elif total_calls > 0:
            # Use available data even if below threshold
            error_rate = (instance.error_count / total_calls) * 100
            success_rate = (instance.success_count / total_calls) * 100

        # Determine status
        status = self._determine_status(
            instance.avg_response_time,
            error_rate,
            instance.health_status,
        )

        # Calculate uptime
        uptime_percent = self._calculate_uptime(mcp_name)

        # Get consecutive failures count
        consecutive_failures = self._get_consecutive_failures(mcp_name)

        metrics = HealthMetrics(
            mcp_name=mcp_name,
            status=status,
            response_time_ms=instance.avg_response_time,
            error_rate_percent=error_rate,
            success_rate_percent=success_rate,
            last_check_time=time.time(),
            uptime_percent=uptime_percent,
            consecutive_failures=consecutive_failures,
            is_loaded=instance.loaded,
            is_enabled=instance.config.enabled,
        )

        # Store in history
        if mcp_name not in self._health_history:
            self._health_history[mcp_name] = []

        self._health_history[mcp_name].append(metrics)

        # Keep last 100 checks
        self._health_history[mcp_name] = self._health_history[mcp_name][-100:]

        # Check for issues
        self._check_for_issues(metrics)

        return metrics

    def check_all_health(self) -> Dict[str, HealthMetrics]:
        """
        Check health of all loaded MCPs

        Returns:
            Dict mapping MCP name to HealthMetrics
        """
        results = {}

        for instance in self.registry.get_all_loaded():
            metrics = self.check_health(instance.config.name)
            results[instance.config.name] = metrics

        self._last_check_time = time.time()

        logger.info(f"Health check completed for {len(results)} MCPs")

        return results

    def _determine_status(
        self,
        response_time_ms: float,
        error_rate: float,
        mcp_reported_status: str,
    ) -> HealthStatus:
        """Determine overall health status"""

        # If MCP reports unhealthy, trust it
        if mcp_reported_status == "unhealthy":
            return HealthStatus.UNHEALTHY

        # Check error rate
        if error_rate >= self.config.error_rate_threshold_percent:
            return HealthStatus.UNHEALTHY

        # Check response time
        if response_time_ms > self.config.response_time_threshold_ms * 2:
            return HealthStatus.UNHEALTHY
        elif response_time_ms > self.config.response_time_threshold_ms:
            return HealthStatus.DEGRADED

        return HealthStatus.HEALTHY

    def _calculate_uptime(self, mcp_name: str) -> float:
        """
        Calculate uptime percentage from history

        Args:
            mcp_name: MCP name

        Returns:
            Uptime percentage (0-100)
        """
        if mcp_name not in self._health_history:
            return 100.0

        history = self._health_history[mcp_name]
        if not history:
            return 100.0

        healthy_count = sum(
            1 for m in history
            if m.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)
        )

        return (healthy_count / len(history)) * 100

    def _get_consecutive_failures(self, mcp_name: str) -> int:
        """Get count of consecutive failures"""
        if mcp_name not in self._health_history:
            return 0

        history = self._health_history[mcp_name]
        if not history:
            return 0

        count = 0
        # Count from most recent backwards
        for metrics in reversed(history):
            if metrics.status == HealthStatus.UNHEALTHY:
                count += 1
            else:
                break

        return count

    def _check_for_issues(self, metrics: HealthMetrics) -> None:
        """
        Check for health issues and take action

        Args:
            metrics: Health metrics to check
        """
        # Check for unhealthy status
        if metrics.status == HealthStatus.UNHEALTHY:
            logger.warning(
                f"MCP {metrics.mcp_name} is UNHEALTHY "
                f"(error_rate={metrics.error_rate_percent:.1f}%, "
                f"response_time={metrics.response_time_ms:.0f}ms)"
            )

            # Check for consecutive failures
            if metrics.consecutive_failures >= self.config.consecutive_failures_threshold:
                self._create_alert(
                    severity="high",
                    mcp_name=metrics.mcp_name,
                    message=f"Consecutive failures: {metrics.consecutive_failures}",
                    metrics=metrics,
                )

                # Auto-disable if configured
                if self.config.auto_disable_unhealthy and metrics.is_enabled:
                    logger.error(
                        f"Auto-disabling MCP {metrics.mcp_name} "
                        f"due to {metrics.consecutive_failures} consecutive failures"
                    )
                    self.registry.disable(metrics.mcp_name)

                    self._create_alert(
                        severity="critical",
                        mcp_name=metrics.mcp_name,
                        message=f"Auto-disabled due to consecutive failures",
                        metrics=metrics,
                    )

        # Check for degraded performance
        elif metrics.status == HealthStatus.DEGRADED:
            logger.info(
                f"MCP {metrics.mcp_name} is DEGRADED "
                f"(response_time={metrics.response_time_ms:.0f}ms)"
            )

            self._create_alert(
                severity="medium",
                mcp_name=metrics.mcp_name,
                message=f"Performance degraded",
                metrics=metrics,
            )

    def _create_alert(
        self,
        severity: str,
        mcp_name: str,
        message: str,
        metrics: HealthMetrics,
    ) -> None:
        """Create a health alert"""
        alert = {
            "timestamp": time.time(),
            "severity": severity,
            "mcp_name": mcp_name,
            "message": message,
            "metrics": {
                "status": metrics.status.value,
                "error_rate": metrics.error_rate_percent,
                "response_time_ms": metrics.response_time_ms,
                "consecutive_failures": metrics.consecutive_failures,
            },
        }

        self._alerts.append(alert)

        # Keep last 1000 alerts
        self._alerts = self._alerts[-1000:]

        logger.warning(f"HEALTH ALERT [{severity}] {mcp_name}: {message}")

    def get_health_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive health report

        Returns:
            Health report with summary and details
        """
        all_health = self.check_all_health()

        # Summary statistics
        total = len(all_health)
        healthy = sum(1 for m in all_health.values() if m.status == HealthStatus.HEALTHY)
        degraded = sum(1 for m in all_health.values() if m.status == HealthStatus.DEGRADED)
        unhealthy = sum(1 for m in all_health.values() if m.status == HealthStatus.UNHEALTHY)

        # Performance statistics
        response_times = [m.response_time_ms for m in all_health.values() if m.response_time_ms > 0]
        error_rates = [m.error_rate_percent for m in all_health.values() if m.error_rate_percent > 0]

        avg_response_time = statistics.mean(response_times) if response_times else 0
        avg_error_rate = statistics.mean(error_rates) if error_rates else 0

        # Recent alerts
        recent_alerts = sorted(
            self._alerts,
            key=lambda x: x["timestamp"],
            reverse=True
        )[:10]

        return {
            "timestamp": time.time(),
            "summary": {
                "total_mcps": total,
                "healthy": healthy,
                "degraded": degraded,
                "unhealthy": unhealthy,
                "health_percentage": (healthy / total * 100) if total > 0 else 0,
            },
            "performance": {
                "avg_response_time_ms": round(avg_response_time, 2),
                "avg_error_rate_percent": round(avg_error_rate, 2),
            },
            "details": {
                name: {
                    "status": metrics.status.value,
                    "response_time_ms": metrics.response_time_ms,
                    "error_rate_percent": metrics.error_rate_percent,
                    "success_rate_percent": metrics.success_rate_percent,
                    "uptime_percent": metrics.uptime_percent,
                    "is_loaded": metrics.is_loaded,
                    "is_enabled": metrics.is_enabled,
                }
                for name, metrics in all_health.items()
            },
            "recent_alerts": recent_alerts,
        }

    def get_trend_analysis(self, mcp_name: str, window_size: int = 20) -> Dict[str, Any]:
        """
        Analyze health trends for an MCP

        Args:
            mcp_name: MCP name
            window_size: Number of recent checks to analyze

        Returns:
            Trend analysis
        """
        if mcp_name not in self._health_history:
            return {"error": "No history available"}

        history = self._health_history[mcp_name][-window_size:]
        if not history:
            return {"error": "No history available"}

        # Response time trend
        response_times = [m.response_time_ms for m in history if m.response_time_ms > 0]
        response_time_trend = "stable"
        if len(response_times) >= 2:
            if response_times[-1] > response_times[0] * 1.5:
                response_time_trend = "increasing"
            elif response_times[-1] < response_times[0] * 0.67:
                response_time_trend = "decreasing"

        # Error rate trend
        error_rates = [m.error_rate_percent for m in history]
        error_rate_trend = "stable"
        if len(error_rates) >= 2:
            if error_rates[-1] > error_rates[0] * 1.5:
                error_rate_trend = "increasing"
            elif error_rates[-1] < error_rates[0] * 0.67:
                error_rate_trend = "decreasing"

        # Health status distribution
        status_counts = {}
        for metrics in history:
            status = metrics.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "mcp_name": mcp_name,
            "window_size": len(history),
            "response_time_trend": response_time_trend,
            "error_rate_trend": error_rate_trend,
            "status_distribution": status_counts,
            "latest_metrics": {
                "status": history[-1].status.value,
                "response_time_ms": history[-1].response_time_ms,
                "error_rate_percent": history[-1].error_rate_percent,
            },
        }

    def clear_alerts(self) -> int:
        """
        Clear all alerts

        Returns:
            Number of alerts cleared
        """
        count = len(self._alerts)
        self._alerts = []
        logger.info(f"Cleared {count} alerts")
        return count

    def get_alerts(
        self,
        severity: Optional[str] = None,
        mcp_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get alerts with optional filtering

        Args:
            severity: Filter by severity
            mcp_name: Filter by MCP name
            limit: Maximum number of alerts to return

        Returns:
            List of alerts
        """
        alerts = self._alerts

        if severity:
            alerts = [a for a in alerts if a["severity"] == severity]

        if mcp_name:
            alerts = [a for a in alerts if a["mcp_name"] == mcp_name]

        # Sort by timestamp descending
        alerts = sorted(alerts, key=lambda x: x["timestamp"], reverse=True)

        return alerts[:limit]

"""
Observability System - Complete monitoring, metrics, tracing and alerting
Integrates Prometheus, OpenTelemetry, structured logging and alerting
"""

import os
import json
import time
import asyncio
import logging
import traceback
from typing import Dict, Any, Optional, List, Callable, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from contextlib import contextmanager, asynccontextmanager
from functools import wraps
from collections import defaultdict, deque
import threading
from enum import Enum

# Import monitoring libraries conditionally
try:
    from prometheus_client import (
        Counter, Histogram, Gauge, Summary,
        CollectorRegistry, generate_latest,
        start_http_server, CONTENT_TYPE_LATEST
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Mocks básicos
    class Counter:
        def inc(self, *args, **kwargs): pass
        def labels(self, **kwargs): return self
    class Histogram:
        def observe(self, *args, **kwargs): pass
        def labels(self, **kwargs): return self
    class Gauge:
        def set(self, *args, **kwargs): pass
        def labels(self, **kwargs): return self
    class Summary:
        def observe(self, *args, **kwargs): pass
        def labels(self, **kwargs): return self
    class CollectorRegistry:
        def __init__(self): pass
    CONTENT_TYPE_LATEST = "text/plain"
    def generate_latest(registry): return b""
    def start_http_server(port): pass

try:
    from opentelemetry import trace, metrics
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False

try:
    import structlog
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False

# Configure base logging
logging.basicConfig(level=logging.INFO)
base_logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class MetricType(Enum):
    """Types of metrics"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class Alert:
    """Alert definition"""
    name: str
    severity: AlertSeverity
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'name': self.name,
            'severity': self.severity.value,
            'message': self.message,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata,
            'resolved': self.resolved
        }


@dataclass
class HealthCheck:
    """Health check result"""
    service: str
    status: str  # healthy, degraded, unhealthy
    latency: float
    message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class StructuredLogger:
    """Structured logging with context"""
    
    def __init__(self, name: str = "nubem", log_level: str = "INFO"):
        self.name = name
        self.context = {}
        
        if STRUCTLOG_AVAILABLE:
            structlog.configure(
                processors=[
                    structlog.stdlib.filter_by_level,
                    structlog.stdlib.add_logger_name,
                    structlog.stdlib.add_log_level,
                    structlog.stdlib.PositionalArgumentsFormatter(),
                    structlog.processors.TimeStamper(fmt="iso"),
                    structlog.processors.StackInfoRenderer(),
                    structlog.processors.format_exc_info,
                    structlog.processors.UnicodeDecoder(),
                    structlog.processors.JSONRenderer()
                ],
                context_class=dict,
                logger_factory=structlog.stdlib.LoggerFactory(),
                cache_logger_on_first_use=True,
            )
            self.logger = structlog.get_logger(name)
        else:
            self.logger = logging.getLogger(name)
            self.logger.setLevel(getattr(logging, log_level))
    
    def bind(self, **kwargs):
        """Add context to logger"""
        self.context.update(kwargs)
        if STRUCTLOG_AVAILABLE:
            self.logger = self.logger.bind(**kwargs)
        return self
    
    def unbind(self, *keys):
        """Remove context from logger"""
        for key in keys:
            self.context.pop(key, None)
        if STRUCTLOG_AVAILABLE:
            self.logger = self.logger.unbind(*keys)
        return self
    
    def _log(self, level: str, message: str, **kwargs):
        """Internal log method"""
        kwargs.update(self.context)
        
        if STRUCTLOG_AVAILABLE:
            getattr(self.logger, level)(message, **kwargs)
        else:
            # Fallback to standard logging
            log_message = f"{message} | {json.dumps(kwargs)}"
            getattr(self.logger, level)(log_message)
    
    def debug(self, message: str, **kwargs):
        self._log('debug', message, **kwargs)
    
    def info(self, message: str, **kwargs):
        self._log('info', message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        self._log('warning', message, **kwargs)
    
    def error(self, message: str, **kwargs):
        self._log('error', message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        self._log('critical', message, **kwargs)
    
    def exception(self, message: str, exc_info=True, **kwargs):
        """Log exception with traceback"""
        if STRUCTLOG_AVAILABLE:
            self.logger.exception(message, exc_info=exc_info, **kwargs)
        else:
            self.logger.exception(message, exc_info=exc_info)


class MetricsCollector:
    """Prometheus metrics collector"""
    
    def __init__(self, namespace: str = "nubem", registry: Optional[CollectorRegistry] = None):
        self.namespace = namespace
        self.registry = registry or CollectorRegistry()
        self.metrics = {}
        
        if not PROMETHEUS_AVAILABLE:
            base_logger.warning("Prometheus client not available, metrics disabled")
            self.enabled = False
        else:
            self.enabled = True
            self._initialize_default_metrics()
    
    def _initialize_default_metrics(self):
        """Initialize default metrics"""
        # Request metrics
        self.metrics['requests_total'] = Counter(
            'requests_total',
            'Total number of requests',
            ['method', 'endpoint', 'status'],
            namespace=self.namespace,
            registry=self.registry
        )
        
        self.metrics['request_duration'] = Histogram(
            'request_duration_seconds',
            'Request duration in seconds',
            ['method', 'endpoint'],
            namespace=self.namespace,
            registry=self.registry
        )
        
        # LLM metrics
        self.metrics['llm_requests'] = Counter(
            'llm_requests_total',
            'Total LLM API requests',
            ['provider', 'model', 'status'],
            namespace=self.namespace,
            registry=self.registry
        )
        
        self.metrics['llm_latency'] = Histogram(
            'llm_latency_seconds',
            'LLM API latency',
            ['provider', 'model'],
            namespace=self.namespace,
            registry=self.registry,
            buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0)
        )
        
        self.metrics['llm_tokens'] = Counter(
            'llm_tokens_total',
            'Total tokens processed',
            ['provider', 'model', 'type'],  # type: input/output
            namespace=self.namespace,
            registry=self.registry
        )
        
        self.metrics['llm_cost'] = Counter(
            'llm_cost_dollars',
            'Total LLM cost in dollars',
            ['provider', 'model'],
            namespace=self.namespace,
            registry=self.registry
        )
        
        # Cache metrics
        self.metrics['cache_hits'] = Counter(
            'cache_hits_total',
            'Cache hits',
            ['cache_level'],  # l1, l2, l3
            namespace=self.namespace,
            registry=self.registry
        )
        
        self.metrics['cache_misses'] = Counter(
            'cache_misses_total',
            'Cache misses',
            namespace=self.namespace,
            registry=self.registry
        )
        
        # System metrics
        self.metrics['active_sessions'] = Gauge(
            'active_sessions',
            'Number of active sessions',
            namespace=self.namespace,
            registry=self.registry
        )
        
        self.metrics['error_rate'] = Counter(
            'errors_total',
            'Total errors',
            ['error_type', 'severity'],
            namespace=self.namespace,
            registry=self.registry
        )
        
        # Business metrics
        self.metrics['queries_processed'] = Counter(
            'queries_processed_total',
            'Total queries processed',
            ['agent', 'status'],
            namespace=self.namespace,
            registry=self.registry
        )
    
    def counter(self, name: str, labels: Optional[List[str]] = None) -> Optional[Counter]:
        """Get or create counter metric"""
        if not self.enabled:
            return None
        
        if name not in self.metrics:
            self.metrics[name] = Counter(
                name,
                f'Counter for {name}',
                labels or [],
                namespace=self.namespace,
                registry=self.registry
            )
        return self.metrics[name]
    
    def gauge(self, name: str, labels: Optional[List[str]] = None) -> Optional[Gauge]:
        """Get or create gauge metric"""
        if not self.enabled:
            return None
        
        if name not in self.metrics:
            self.metrics[name] = Gauge(
                name,
                f'Gauge for {name}',
                labels or [],
                namespace=self.namespace,
                registry=self.registry
            )
        return self.metrics[name]
    
    def histogram(self, name: str, labels: Optional[List[str]] = None, 
                  buckets: Optional[tuple] = None) -> Optional[Histogram]:
        """Get or create histogram metric"""
        if not self.enabled:
            return None
        
        if name not in self.metrics:
            self.metrics[name] = Histogram(
                name,
                f'Histogram for {name}',
                labels or [],
                namespace=self.namespace,
                registry=self.registry,
                buckets=buckets or Histogram.DEFAULT_BUCKETS
            )
        return self.metrics[name]
    
    def summary(self, name: str, labels: Optional[List[str]] = None) -> Optional[Summary]:
        """Get or create summary metric"""
        if not self.enabled:
            return None
        
        if name not in self.metrics:
            self.metrics[name] = Summary(
                name,
                f'Summary for {name}',
                labels or [],
                namespace=self.namespace,
                registry=self.registry
            )
        return self.metrics[name]
    
    def export_metrics(self) -> bytes:
        """Export metrics in Prometheus format"""
        if not self.enabled:
            return b""
        return generate_latest(self.registry)


class Tracer:
    """OpenTelemetry tracer wrapper"""
    
    def __init__(self, service_name: str = "nubem", endpoint: Optional[str] = None):
        self.service_name = service_name
        self.endpoint = endpoint
        
        if not OPENTELEMETRY_AVAILABLE:
            base_logger.warning("OpenTelemetry not available, tracing disabled")
            self.enabled = False
            self.tracer = None
        else:
            self.enabled = True
            self._initialize_tracer()
    
    def _initialize_tracer(self):
        """Initialize OpenTelemetry tracer"""
        resource = Resource.create({
            "service.name": self.service_name,
            "service.version": "1.0.0"
        })
        
        provider = TracerProvider(resource=resource)
        
        if self.endpoint:
            exporter = OTLPSpanExporter(endpoint=self.endpoint)
            processor = BatchSpanProcessor(exporter)
            provider.add_span_processor(processor)
        
        trace.set_tracer_provider(provider)
        self.tracer = trace.get_tracer(__name__)
        
        # Auto-instrument HTTP requests
        RequestsInstrumentor().instrument()
    
    @contextmanager
    def span(self, name: str, attributes: Optional[Dict] = None):
        """Create a trace span"""
        if not self.enabled:
            yield None
            return
        
        with self.tracer.start_as_current_span(name) as span:
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)
            
            try:
                yield span
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise
    
    def get_current_span(self):
        """Get current active span"""
        if not self.enabled:
            return None
        return trace.get_current_span()


class AlertManager:
    """Alert management and notification system"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.alerts: List[Alert] = []
        self.alert_rules: Dict[str, Callable] = {}
        self.notification_channels: List[Callable] = []
        self.alert_history = deque(maxlen=1000)
        self.lock = threading.Lock()
    
    def add_rule(self, name: str, condition: Callable, 
                 severity: AlertSeverity = AlertSeverity.WARNING):
        """Add alert rule"""
        self.alert_rules[name] = {
            'condition': condition,
            'severity': severity
        }
    
    def add_notification_channel(self, channel: Callable):
        """Add notification channel (email, Slack, etc.)"""
        self.notification_channels.append(channel)
    
    async def trigger(self, name: str, message: str, 
                     severity: Optional[AlertSeverity] = None,
                     metadata: Optional[Dict] = None):
        """Trigger an alert"""
        alert = Alert(
            name=name,
            severity=severity or AlertSeverity.WARNING,
            message=message,
            metadata=metadata or {}
        )
        
        with self.lock:
            self.alerts.append(alert)
            self.alert_history.append(alert)
        
        # Send notifications
        await self._send_notifications(alert)
        
        base_logger.warning(f"Alert triggered: {name} - {message}")
    
    async def _send_notifications(self, alert: Alert):
        """Send alert notifications through all channels"""
        for channel in self.notification_channels:
            try:
                if asyncio.iscoroutinefunction(channel):
                    await channel(alert)
                else:
                    await asyncio.to_thread(channel, alert)
            except Exception as e:
                base_logger.error(f"Error sending notification: {e}")
    
    async def check_rules(self, metrics: Dict[str, Any]):
        """Check alert rules against current metrics"""
        for name, rule in self.alert_rules.items():
            try:
                condition = rule['condition']
                if condition(metrics):
                    await self.trigger(
                        name=name,
                        message=f"Alert rule {name} triggered",
                        severity=rule['severity'],
                        metadata={'metrics': metrics}
                    )
            except Exception as e:
                base_logger.error(f"Error checking alert rule {name}: {e}")
    
    def resolve(self, alert_name: str):
        """Mark alert as resolved"""
        with self.lock:
            for alert in self.alerts:
                if alert.name == alert_name and not alert.resolved:
                    alert.resolved = True
                    base_logger.info(f"Alert resolved: {alert_name}")
    
    def get_active_alerts(self) -> List[Alert]:
        """Get all active (unresolved) alerts"""
        with self.lock:
            return [a for a in self.alerts if not a.resolved]
    
    def get_alert_history(self, limit: int = 100) -> List[Alert]:
        """Get alert history"""
        with self.lock:
            return list(self.alert_history)[-limit:]


class ObservabilitySystem:
    """
    Unified observability system with metrics, tracing, logging, and alerting
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        
        # Initialize components
        self.logger = StructuredLogger(
            name=self.config.get('logger_name', 'nubem'),
            log_level=self.config.get('log_level', 'INFO')
        )
        
        self.metrics = MetricsCollector(
            namespace=self.config.get('metrics_namespace', 'nubem')
        )
        
        self.tracer = Tracer(
            service_name=self.config.get('service_name', 'nubem'),
            endpoint=self.config.get('otlp_endpoint')
        )
        
        self.alerts = AlertManager(config=self.config.get('alerts', {}))
        
        # Health checks
        self.health_checks: Dict[str, Callable] = {}
        
        # Performance tracking
        self.performance_stats = defaultdict(list)
        
        # Initialize alert rules
        self._setup_default_alerts()
        
        # Start metrics server if enabled
        if self.config.get('metrics_port'):
            self._start_metrics_server()
    
    def _setup_default_alerts(self):
        """Setup default alert rules"""
        # High error rate alert
        self.alerts.add_rule(
            name='high_error_rate',
            condition=lambda m: m.get('error_rate', 0) > 0.05,
            severity=AlertSeverity.ERROR
        )
        
        # High latency alert
        self.alerts.add_rule(
            name='high_latency',
            condition=lambda m: m.get('p95_latency', 0) > 5.0,
            severity=AlertSeverity.WARNING
        )
        
        # Low cache hit rate
        self.alerts.add_rule(
            name='low_cache_hit_rate',
            condition=lambda m: m.get('cache_hit_rate', 1) < 0.5,
            severity=AlertSeverity.INFO
        )
        
        # High LLM cost
        self.alerts.add_rule(
            name='high_llm_cost',
            condition=lambda m: m.get('llm_cost_per_hour', 0) > 10.0,
            severity=AlertSeverity.WARNING
        )
    
    def _start_metrics_server(self):
        """Start Prometheus metrics server"""
        if PROMETHEUS_AVAILABLE:
            port = self.config.get('metrics_port', 9090)
            start_http_server(port, registry=self.metrics.registry)
            self.logger.info(f"Metrics server started", port=port)
    
    @contextmanager
    def track_operation(self, operation: str, **attributes):
        """
        Track an operation with metrics and tracing
        
        Args:
            operation: Operation name
            **attributes: Additional attributes to track
        """
        start_time = time.time()
        
        # Start trace span
        with self.tracer.span(operation, attributes) as span:
            try:
                # Add to logger context
                self.logger.bind(operation=operation, **attributes)
                
                yield span
                
                # Success metrics
                duration = time.time() - start_time
                self.metrics.counter(f'{operation}_success').inc()
                self.metrics.histogram(f'{operation}_duration').observe(duration)
                
                # Track performance
                self.performance_stats[operation].append(duration)
                
                self.logger.info(f"Operation completed", 
                               duration=duration, 
                               status='success')
                
            except Exception as e:
                # Error metrics
                duration = time.time() - start_time
                self.metrics.counter(f'{operation}_error').inc()
                self.metrics.counter('errors_total', ['error_type', 'severity']).labels(
                    error_type=type(e).__name__,
                    severity='error'
                ).inc()
                
                self.logger.exception(f"Operation failed",
                                    duration=duration,
                                    error=str(e),
                                    status='error')
                
                # Trigger alert if critical
                if 'critical' in attributes.get('tags', []):
                    asyncio.create_task(self.alerts.trigger(
                        name=f'{operation}_failed',
                        message=f"Critical operation {operation} failed: {str(e)}",
                        severity=AlertSeverity.CRITICAL,
                        metadata={'error': str(e), 'traceback': traceback.format_exc()}
                    ))
                
                raise
            
            finally:
                # Clean up logger context
                self.logger.unbind('operation')
    
    @asynccontextmanager
    async def track_async_operation(self, operation: str, **attributes):
        """Async version of track_operation"""
        start_time = time.time()
        
        with self.tracer.span(operation, attributes) as span:
            try:
                self.logger.bind(operation=operation, **attributes)
                
                yield span
                
                duration = time.time() - start_time
                self.metrics.counter(f'{operation}_success').inc()
                self.metrics.histogram(f'{operation}_duration').observe(duration)
                self.performance_stats[operation].append(duration)
                
                self.logger.info(f"Async operation completed",
                               duration=duration,
                               status='success')
                
            except Exception as e:
                duration = time.time() - start_time
                self.metrics.counter(f'{operation}_error').inc()
                
                self.logger.exception(f"Async operation failed",
                                    duration=duration,
                                    error=str(e),
                                    status='error')
                
                if 'critical' in attributes.get('tags', []):
                    await self.alerts.trigger(
                        name=f'{operation}_failed',
                        message=f"Critical async operation {operation} failed: {str(e)}",
                        severity=AlertSeverity.CRITICAL,
                        metadata={'error': str(e), 'traceback': traceback.format_exc()}
                    )
                
                raise
            
            finally:
                self.logger.unbind('operation')
    
    def track_llm_call(self, provider: str, model: str, tokens_in: int, 
                       tokens_out: int, latency: float, cost: float, 
                       success: bool = True):
        """Track LLM API call metrics"""
        status = 'success' if success else 'error'
        
        self.metrics.counter('llm_requests', ['provider', 'model', 'status']).labels(
            provider=provider, model=model, status=status
        ).inc()
        
        if success:
            self.metrics.histogram('llm_latency', ['provider', 'model']).labels(
                provider=provider, model=model
            ).observe(latency)
            
            self.metrics.counter('llm_tokens', ['provider', 'model', 'type']).labels(
                provider=provider, model=model, type='input'
            ).inc(tokens_in)
            
            self.metrics.counter('llm_tokens', ['provider', 'model', 'type']).labels(
                provider=provider, model=model, type='output'
            ).inc(tokens_out)
            
            self.metrics.counter('llm_cost', ['provider', 'model']).labels(
                provider=provider, model=model
            ).inc(cost)
    
    def track_cache_access(self, hit: bool, level: str = 'l1'):
        """Track cache access"""
        if hit:
            self.metrics.counter('cache_hits', ['cache_level']).labels(
                cache_level=level
            ).inc()
        else:
            self.metrics.counter('cache_misses').inc()
    
    def add_health_check(self, name: str, check_fn: Callable):
        """Add a health check"""
        self.health_checks[name] = check_fn
    
    async def check_health(self) -> Dict[str, HealthCheck]:
        """Run all health checks"""
        results = {}
        
        for name, check_fn in self.health_checks.items():
            start_time = time.time()
            try:
                if asyncio.iscoroutinefunction(check_fn):
                    status = await check_fn()
                else:
                    status = await asyncio.to_thread(check_fn)
                
                latency = time.time() - start_time
                
                results[name] = HealthCheck(
                    service=name,
                    status='healthy' if status else 'unhealthy',
                    latency=latency,
                    message=None if status else 'Check failed'
                )
            except Exception as e:
                latency = time.time() - start_time
                results[name] = HealthCheck(
                    service=name,
                    status='unhealthy',
                    latency=latency,
                    message=str(e)
                )
        
        return results
    
    def get_dashboard_config(self) -> Dict[str, Any]:
        """Get Grafana dashboard configuration"""
        return {
            'title': 'NubemSuperFClaude Monitoring',
            'panels': [
                {
                    'title': 'Request Rate',
                    'type': 'graph',
                    'targets': [
                        {'expr': 'rate(nubem_requests_total[5m])'}
                    ]
                },
                {
                    'title': 'Error Rate',
                    'type': 'graph',
                    'targets': [
                        {'expr': 'rate(nubem_errors_total[5m])'}
                    ]
                },
                {
                    'title': 'LLM Latency (P95)',
                    'type': 'graph',
                    'targets': [
                        {'expr': 'histogram_quantile(0.95, rate(nubem_llm_latency_seconds_bucket[5m]))'}
                    ]
                },
                {
                    'title': 'Cache Hit Rate',
                    'type': 'gauge',
                    'targets': [
                        {'expr': 'rate(nubem_cache_hits_total[5m]) / (rate(nubem_cache_hits_total[5m]) + rate(nubem_cache_misses_total[5m]))'}
                    ]
                },
                {
                    'title': 'LLM Cost Rate ($/hour)',
                    'type': 'graph',
                    'targets': [
                        {'expr': 'rate(nubem_llm_cost_dollars[1h]) * 3600'}
                    ]
                },
                {
                    'title': 'Active Sessions',
                    'type': 'stat',
                    'targets': [
                        {'expr': 'nubem_active_sessions'}
                    ]
                }
            ]
        }
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of current metrics"""
        summary = {
            'active_alerts': len(self.alerts.get_active_alerts()),
            'performance': {}
        }
        
        # Calculate performance stats
        for operation, durations in self.performance_stats.items():
            if durations:
                summary['performance'][operation] = {
                    'count': len(durations),
                    'avg': sum(durations) / len(durations),
                    'min': min(durations),
                    'max': max(durations),
                    'p95': sorted(durations)[int(len(durations) * 0.95)] if len(durations) > 1 else durations[0]
                }
        
        return summary


def monitored(operation_name: Optional[str] = None):
    """
    Decorator to monitor function execution
    
    Args:
        operation_name: Custom operation name (defaults to function name)
    """
    def decorator(func):
        name = operation_name or func.__name__
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Get or create observability instance
            obs = ObservabilitySystem()
            
            async with obs.track_async_operation(name):
                return await func(*args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            obs = ObservabilitySystem()
            
            with obs.track_operation(name):
                return func(*args, **kwargs)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
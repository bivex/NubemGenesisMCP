"""
Observability and monitoring for NubemSuperFClaude
Provides metrics, tracing, and health checks
"""

import time
import json
import psutil
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
import threading
from collections import deque, defaultdict
from dataclasses import dataclass, asdict


logger = logging.getLogger(__name__)


@dataclass
class Metric:
    """Represents a single metric point"""
    name: str
    value: float
    timestamp: datetime
    tags: Dict[str, str] = None
    type: str = 'gauge'  # gauge, counter, histogram


class MetricsCollector:
    """Collects and aggregates metrics"""
    
    def __init__(self, max_history: int = 1000):
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self.counters: Dict[str, float] = defaultdict(float)
        self.lock = threading.Lock()
    
    def record_gauge(self, name: str, value: float, tags: Dict[str, str] = None):
        """Record a gauge metric (point-in-time value)"""
        with self.lock:
            metric = Metric(name, value, datetime.now(), tags, 'gauge')
            self.metrics[name].append(metric)
    
    def increment_counter(self, name: str, value: float = 1, tags: Dict[str, str] = None):
        """Increment a counter metric"""
        with self.lock:
            self.counters[name] += value
            metric = Metric(name, self.counters[name], datetime.now(), tags, 'counter')
            self.metrics[name].append(metric)
    
    def record_histogram(self, name: str, value: float, tags: Dict[str, str] = None):
        """Record a histogram metric (for distributions)"""
        with self.lock:
            metric = Metric(name, value, datetime.now(), tags, 'histogram')
            self.metrics[name].append(metric)
    
    def get_metrics(self, name: str = None, last_n_minutes: int = None) -> List[Metric]:
        """Get metrics, optionally filtered by name and time"""
        with self.lock:
            if name:
                metrics = list(self.metrics.get(name, []))
            else:
                metrics = []
                for metric_list in self.metrics.values():
                    metrics.extend(list(metric_list))
            
            if last_n_minutes:
                cutoff = datetime.now() - timedelta(minutes=last_n_minutes)
                metrics = [m for m in metrics if m.timestamp > cutoff]
            
            return metrics
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics for all metrics"""
        with self.lock:
            summary = {}
            
            for name, metric_list in self.metrics.items():
                if not metric_list:
                    continue
                
                values = [m.value for m in metric_list]
                summary[name] = {
                    'count': len(values),
                    'last': values[-1] if values else None,
                    'min': min(values) if values else None,
                    'max': max(values) if values else None,
                    'avg': sum(values) / len(values) if values else None,
                    'type': metric_list[-1].type if metric_list else None
                }
            
            # Add counters
            for name, value in self.counters.items():
                if name not in summary:
                    summary[name] = {
                        'count': 1,
                        'last': value,
                        'total': value,
                        'type': 'counter'
                    }
            
            return summary


class HealthChecker:
    """System health checks"""
    
    def __init__(self):
        self.checks = {}
        self.last_check = {}
    
    def register_check(self, name: str, check_func, interval_seconds: int = 60):
        """Register a health check function"""
        self.checks[name] = {
            'func': check_func,
            'interval': interval_seconds
        }
    
    def run_checks(self) -> Dict[str, Dict[str, Any]]:
        """Run all registered health checks"""
        results = {}
        now = datetime.now()
        
        for name, check in self.checks.items():
            # Check if enough time has passed
            last_run = self.last_check.get(name)
            if last_run and (now - last_run).total_seconds() < check['interval']:
                continue
            
            try:
                start = time.time()
                result = check['func']()
                duration = time.time() - start
                
                results[name] = {
                    'status': 'healthy' if result else 'unhealthy',
                    'result': result,
                    'duration_ms': duration * 1000,
                    'timestamp': now.isoformat()
                }
                
                self.last_check[name] = now
                
            except Exception as e:
                results[name] = {
                    'status': 'error',
                    'error': str(e),
                    'timestamp': now.isoformat()
                }
        
        return results
    
    def get_overall_health(self) -> str:
        """Get overall system health status"""
        results = self.run_checks()
        
        if not results:
            return 'unknown'
        
        if any(r['status'] == 'error' for r in results.values()):
            return 'critical'
        
        if any(r['status'] == 'unhealthy' for r in results.values()):
            return 'degraded'
        
        return 'healthy'


class PerformanceTracker:
    """Track performance metrics for functions"""
    
    def __init__(self, metrics_collector: MetricsCollector = None):
        self.metrics = metrics_collector or MetricsCollector()
    
    def track(self, name: str = None):
        """Decorator to track function performance"""
        def decorator(func):
            nonlocal name
            if not name:
                name = f"{func.__module__}.{func.__name__}"
            
            @wraps(func)
            def wrapper(*args, **kwargs):
                start = time.time()
                error = None
                
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    error = e
                    raise
                finally:
                    duration = time.time() - start
                    
                    # Record metrics
                    self.metrics.record_histogram(f"{name}.duration", duration * 1000)
                    self.metrics.increment_counter(f"{name}.calls")
                    
                    if error:
                        self.metrics.increment_counter(f"{name}.errors")
                    
                    # Log if slow
                    if duration > 1.0:
                        logger.warning(f"Slow function: {name} took {duration:.2f}s")
            
            return wrapper
        return decorator


class SystemMonitor:
    """Monitor system resources"""
    
    def __init__(self, metrics_collector: MetricsCollector = None):
        self.metrics = metrics_collector or MetricsCollector()
        self.process = psutil.Process()
    
    def collect_system_metrics(self):
        """Collect system resource metrics"""
        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        self.metrics.record_gauge('system.cpu.percent', cpu_percent)
        
        # Memory
        memory = psutil.virtual_memory()
        self.metrics.record_gauge('system.memory.percent', memory.percent)
        self.metrics.record_gauge('system.memory.used_gb', memory.used / (1024**3))
        self.metrics.record_gauge('system.memory.available_gb', memory.available / (1024**3))
        
        # Process-specific
        process_memory = self.process.memory_info()
        self.metrics.record_gauge('process.memory.rss_mb', process_memory.rss / (1024**2))
        self.metrics.record_gauge('process.memory.vms_mb', process_memory.vms / (1024**2))
        
        process_cpu = self.process.cpu_percent(interval=0.1)
        self.metrics.record_gauge('process.cpu.percent', process_cpu)
        
        # Disk (if applicable)
        try:
            disk = psutil.disk_usage('/')
            self.metrics.record_gauge('system.disk.percent', disk.percent)
            self.metrics.record_gauge('system.disk.free_gb', disk.free / (1024**3))
        except:
            pass
        
        # Network (optional)
        try:
            net_io = psutil.net_io_counters()
            self.metrics.record_counter('system.network.bytes_sent', net_io.bytes_sent)
            self.metrics.record_counter('system.network.bytes_recv', net_io.bytes_recv)
        except:
            pass


# Global instances
_metrics_collector = MetricsCollector()
_health_checker = HealthChecker()
_performance_tracker = PerformanceTracker(_metrics_collector)
_system_monitor = SystemMonitor(_metrics_collector)


# Convenience functions
def record_metric(name: str, value: float, type: str = 'gauge', tags: Dict = None):
    """Record a metric"""
    if type == 'gauge':
        _metrics_collector.record_gauge(name, value, tags)
    elif type == 'counter':
        _metrics_collector.increment_counter(name, value, tags)
    elif type == 'histogram':
        _metrics_collector.record_histogram(name, value, tags)


def track_performance(name: str = None):
    """Decorator to track function performance"""
    return _performance_tracker.track(name)


def collect_system_metrics():
    """Collect current system metrics"""
    _system_monitor.collect_system_metrics()


def get_metrics_summary() -> Dict[str, Any]:
    """Get summary of all metrics"""
    return _metrics_collector.get_summary()


def get_health_status() -> Dict[str, Any]:
    """Get health status"""
    return {
        'status': _health_checker.get_overall_health(),
        'checks': _health_checker.run_checks(),
        'timestamp': datetime.now().isoformat()
    }


# Register default health checks
def _check_memory():
    """Check if memory usage is acceptable"""
    memory = psutil.virtual_memory()
    return memory.percent < 90  # Less than 90% used


def _check_disk():
    """Check if disk space is available"""
    disk = psutil.disk_usage('/')
    return disk.percent < 95  # Less than 95% used


def _check_api_keys():
    """Check if API keys are configured"""
    try:
        from config.settings import get_settings
        settings = get_settings()
        return len(settings.get_available_providers()) > 0
    except:
        return False


# Register default checks
_health_checker.register_check('memory', _check_memory, 60)
_health_checker.register_check('disk', _check_disk, 300)
_health_checker.register_check('api_keys', _check_api_keys, 3600)


# Export metrics in different formats
def export_prometheus() -> str:
    """Export metrics in Prometheus format"""
    lines = []
    summary = get_metrics_summary()
    
    for name, stats in summary.items():
        # Convert dots to underscores for Prometheus
        prom_name = name.replace('.', '_')
        
        if stats['type'] == 'counter':
            lines.append(f"# TYPE {prom_name} counter")
            lines.append(f"{prom_name} {stats.get('total', stats.get('last', 0))}")
        elif stats['type'] == 'gauge':
            lines.append(f"# TYPE {prom_name} gauge")
            lines.append(f"{prom_name} {stats.get('last', 0)}")
        elif stats['type'] == 'histogram':
            lines.append(f"# TYPE {prom_name} summary")
            lines.append(f"{prom_name}_count {stats.get('count', 0)}")
            lines.append(f"{prom_name}_sum {stats.get('avg', 0) * stats.get('count', 0)}")
    
    return '\n'.join(lines)


def export_json() -> str:
    """Export metrics in JSON format"""
    return json.dumps({
        'metrics': get_metrics_summary(),
        'health': get_health_status(),
        'timestamp': datetime.now().isoformat()
    }, indent=2, default=str)


if __name__ == "__main__":
    # Test observability
    print("🔍 Testing Observability System")
    print("=" * 50)
    
    # Collect system metrics
    collect_system_metrics()
    
    # Test performance tracking
    @track_performance("test_function")
    def slow_function():
        time.sleep(0.1)
        return "done"
    
    slow_function()
    
    # Record some custom metrics
    record_metric("custom.metric", 42.0, 'gauge')
    record_metric("custom.counter", 1, 'counter')
    
    # Get summary
    print("\n📊 Metrics Summary:")
    summary = get_metrics_summary()
    for name, stats in summary.items():
        print(f"  {name}: {stats}")
    
    # Check health
    print("\n🏥 Health Status:")
    health = get_health_status()
    print(f"  Overall: {health['status']}")
    for check, result in health['checks'].items():
        print(f"  {check}: {result['status']}")
    
    # Export formats
    print("\n📤 Export Formats:")
    print("  Prometheus format available")
    print("  JSON format available")
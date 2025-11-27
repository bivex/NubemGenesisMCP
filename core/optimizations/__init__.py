"""
NubemSuperFClaude Optimizations Module
Performance and cost optimizations for multi-LLM system
"""

from .api_selector import SmartAPISelector
from .cost_monitor import APIUsageMonitor, CostTracker
from .intelligent_cache import IntelligentCache
from .circuit_breaker import CircuitBreaker, ResilientAPIManager
from .task_optimizer import TaskOptimizer
from .load_balancer import WeightedLoadBalancer
from .persona_scaler import PersonaAutoScaler
from .rate_limiter import SmartRateLimiter

__all__ = [
    'SmartAPISelector',
    'APIUsageMonitor',
    'CostTracker',
    'IntelligentCache',
    'CircuitBreaker',
    'ResilientAPIManager',
    'TaskOptimizer',
    'WeightedLoadBalancer',
    'PersonaAutoScaler',
    'SmartRateLimiter'
]

# Version
__version__ = '2.0.0'
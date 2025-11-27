"""
Structured Logging System
"""

import structlog
import json
from datetime import datetime
from typing import Any, Dict

# Configure structured logging
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

def get_logger(name: str):
    """Get a structured logger instance"""
    return structlog.get_logger(name)

class StructuredLogger:
    """Enhanced structured logging with metrics"""
    
    def __init__(self, name: str):
        self.logger = get_logger(name)
        
    def log_api_call(self, api: str, model: str, **kwargs):
        """Log API call with structured data"""
        self.logger.info(
            "api_call",
            api=api,
            model=model,
            timestamp=datetime.now().isoformat(),
            **kwargs
        )
    
    def log_error(self, error: Exception, context: Dict[str, Any]):
        """Log error with context"""
        self.logger.error(
            "error_occurred",
            error_type=type(error).__name__,
            error_message=str(error),
            context=context,
            timestamp=datetime.now().isoformat()
        )
    
    def log_performance(self, operation: str, duration: float, **kwargs):
        """Log performance metrics"""
        self.logger.info(
            "performance_metric",
            operation=operation,
            duration_ms=duration * 1000,
            timestamp=datetime.now().isoformat(),
            **kwargs
        )
#!/usr/bin/env python3
"""
Configuración centralizada de logging
"""

import logging
import logging.handlers
from pathlib import Path
from datetime import datetime
import json

class StructuredFormatter(logging.Formatter):
    """Formatter para logs estructurados (JSON)"""
    
    def format(self, record):
        log_obj = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add extra fields if present
        if hasattr(record, 'user_id'):
            log_obj['user_id'] = record.user_id
        if hasattr(record, 'session_id'):
            log_obj['session_id'] = record.session_id
        if hasattr(record, 'persona'):
            log_obj['persona'] = record.persona
        if hasattr(record, 'model'):
            log_obj['model'] = record.model
        if hasattr(record, 'cost'):
            log_obj['cost'] = record.cost
            
        if record.exc_info:
            log_obj['exception'] = self.formatException(record.exc_info)
            
        return json.dumps(log_obj)


def setup_logging(
    log_level=logging.INFO,
    log_dir="logs",
    enable_console=True,
    enable_file=True,
    enable_structured=False
):
    """
    Configura logging centralizado para toda la aplicación
    
    Args:
        log_level: Nivel de logging
        log_dir: Directorio para logs
        enable_console: Habilitar output a consola
        enable_file: Habilitar output a archivo
        enable_structured: Usar formato JSON estructurado
    """
    
    # Create logs directory
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    root_logger.handlers = []
    
    # Console handler
    if enable_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        
        if enable_structured:
            console_handler.setFormatter(StructuredFormatter())
        else:
            console_format = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(console_format)
        
        root_logger.addHandler(console_handler)
    
    # File handler with rotation
    if enable_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_path / 'nubemclaude.log',
            maxBytes=10_485_760,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(log_level)
        
        if enable_structured:
            file_handler.setFormatter(StructuredFormatter())
        else:
            file_format = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
            )
            file_handler.setFormatter(file_format)
        
        root_logger.addHandler(file_handler)
    
    # Error file handler (always enabled)
    error_handler = logging.handlers.RotatingFileHandler(
        log_path / 'errors.log',
        maxBytes=10_485_760,
        backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s\n%(exc_info)s'
    )
    error_handler.setFormatter(error_format)
    root_logger.addHandler(error_handler)
    
    # Configure specific loggers
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    
    root_logger.info(f"Logging configured - Level: {logging.getLevelName(log_level)}, Dir: {log_path}")
    
    return root_logger


# Performance logger for metrics
class PerformanceLogger:
    """Logger especializado para métricas de rendimiento"""
    
    def __init__(self, logger_name="performance"):
        self.logger = logging.getLogger(logger_name)
    
    def log_api_call(self, api, model, latency, tokens=None, cost=None, **kwargs):
        """Log API call metrics"""
        extra = {
            'api': api,
            'model': model,
            'latency': latency,
            'tokens': tokens,
            'cost': cost
        }
        extra.update(kwargs)
        
        self.logger.info(
            f"API call to {api}/{model} - {latency:.2f}s",
            extra=extra
        )
    
    def log_orchestration(self, strategy, task_type, execution_time, **kwargs):
        """Log orchestration metrics"""
        extra = {
            'strategy': strategy,
            'task_type': task_type,
            'execution_time': execution_time
        }
        extra.update(kwargs)
        
        self.logger.info(
            f"Orchestration with {strategy} - {execution_time:.2f}s",
            extra=extra
        )


# Usage example
if __name__ == "__main__":
    # Setup logging
    setup_logging(
        log_level=logging.DEBUG,
        enable_structured=True
    )
    
    # Test logging
    logger = logging.getLogger(__name__)
    logger.info("Logging system initialized")
    logger.debug("Debug message")
    logger.warning("Warning message")
    
    # Test performance logging
    perf_logger = PerformanceLogger()
    perf_logger.log_api_call(
        api="openai",
        model="gpt-4",
        latency=1.23,
        tokens=500,
        cost=0.05
    )
    
    # Test error logging
    try:
        1 / 0
    except Exception as e:
        logger.error("Division by zero error", exc_info=True)
    
    print("✅ Logging test completed - Check logs/ directory")
"""
Unified Settings Configuration
Central configuration management with environment variables and file support
"""

import os
import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Union, List
import logging

logger = logging.getLogger(__name__)


class Settings:
    """
    Central configuration management for NubemSuperFClaude
    Simplified version without pydantic dependency
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize settings from environment and config files
        
        Args:
            config_path: Optional path to configuration file
        """
        self.config: Dict[str, Any] = {}
        self.env_prefix = "NUBEM_"
        
        # Load in order of precedence (later overrides earlier)
        self._load_defaults()
        self._load_from_file(config_path)
        self._load_from_env()
        
        # Create necessary directories
        self._create_directories()
        
        logger.info(f"Settings loaded with {len(self.config)} configuration items")
    
    def _load_defaults(self):
        """Load default configuration"""
        self.config.update({
            # Application settings
            'app_name': 'NubemSuperFClaude',
            'version': '2.0.0',
            'environment': 'development',
            'debug': False,
            'log_level': 'INFO',
            
            # API settings
            'api_host': '0.0.0.0',
            'api_port': 8000,
            'cors_origins': ['*'],
            
            # LLM settings
            'default_llm_provider': 'auto',
            'llm_timeout': 30,
            'llm_max_retries': 3,
            'llm_temperature': 0.7,
            'llm_max_tokens': 4096,
            
            # Cache settings
            'cache_enabled': True,
            'cache_local_size': 1000,
            'cache_ttl': 3600,
            'redis_enabled': True,
            'redis_host': 'localhost',
            'redis_port': 6379,
            
            # Secrets management
            'secrets_provider': 'auto',
            'gcp_project': os.getenv('GOOGLE_CLOUD_PROJECT'),
            'aws_region': os.getenv('AWS_REGION', 'us-east-1'),
            
            # Observability
            'metrics_enabled': True,
            'metrics_port': 9090,
            
            # Paths
            'data_dir': './data',
            'logs_dir': './logs',
            'cache_dir': './.cache',
            'secrets_dir': './.secrets',
        })
    
    def _load_from_file(self, config_path: Optional[str]):
        """Load configuration from file"""
        if not config_path:
            # Try default locations
            default_paths = [
                'config.yaml',
                'config.json',
                '.nubem.yaml',
                '.nubem.json'
            ]
            
            for path in default_paths:
                if os.path.exists(path):
                    config_path = path
                    break
        
        if not config_path or not os.path.exists(config_path):
            return
        
        try:
            with open(config_path, 'r') as f:
                if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                    file_config = yaml.safe_load(f)
                elif config_path.endswith('.json'):
                    file_config = json.load(f)
                else:
                    return
            
            if file_config:
                self.config.update(file_config)
                logger.info(f"Loaded configuration from {config_path}")
        
        except Exception as e:
            logger.error(f"Error loading config file {config_path}: {e}")
    
    def _load_from_env(self):
        """Load configuration from environment variables"""
        # Direct mappings
        env_mappings = {
            'NUBEM_DEBUG': ('debug', lambda x: x.lower() == 'true'),
            'NUBEM_LOG_LEVEL': ('log_level', str),
            'NUBEM_API_PORT': ('api_port', int),
            'NUBEM_REDIS_HOST': ('redis_host', str),
            'NUBEM_REDIS_PORT': ('redis_port', int),
            'NUBEM_METRICS_PORT': ('metrics_port', int),
            'NUBEM_ENVIRONMENT': ('environment', str),
            
            # API Keys
            'OPENAI_API_KEY': ('openai_api_key', str),
            'ANTHROPIC_API_KEY': ('anthropic_api_key', str),
            'CLAUDE_API_KEY': ('anthropic_api_key', str),
            'GEMINI_API_KEY': ('gemini_api_key', str),
            'GOOGLE_API_KEY': ('gemini_api_key', str),
            'GROQ_API_KEY': ('groq_api_key', str),
            'TOGETHER_API_KEY': ('together_api_key', str),
        }
        
        for env_key, (config_key, converter) in env_mappings.items():
            env_value = os.getenv(env_key)
            if env_value is not None:
                try:
                    self.config[config_key] = converter(env_value)
                except Exception as e:
                    logger.warning(f"Error converting env var {env_key}: {e}")
    
    def _create_directories(self):
        """Create necessary directories"""
        for key in ['data_dir', 'logs_dir', 'cache_dir', 'secrets_dir']:
            path = Path(self.config.get(key, '.'))
            path.mkdir(parents=True, exist_ok=True)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any):
        """Set configuration value"""
        self.config[key] = value
    
    def get_api_keys(self) -> Dict[str, Optional[str]]:
        """Get all configured API keys"""
        return {
            'openai': self.get('openai_api_key'),
            'anthropic': self.get('anthropic_api_key'),
            'gemini': self.get('gemini_api_key'),
            'groq': self.get('groq_api_key'),
            'together': self.get('together_api_key')
        }
    
    def validate(self) -> Dict[str, List[str]]:
        """Validate configuration"""
        errors = []
        warnings = []
        
        # Check for API keys
        has_api_key = any(self.get_api_keys().values())
        if not has_api_key:
            warnings.append("No LLM API keys configured")
        
        # Check port conflicts
        if self.get('api_port') == self.get('metrics_port'):
            errors.append("API port and metrics port cannot be the same")
        
        return {'errors': errors, 'warnings': warnings}
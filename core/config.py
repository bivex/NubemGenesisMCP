"""
Configuration management for NubemClaude Framework
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from typing import Dict, Any, Optional
try:
    from pydantic import Field
    from pydantic_settings import BaseSettings
    PYDANTIC_V2 = True
except ImportError:
    try:
        from pydantic import BaseSettings, Field
        PYDANTIC_V2 = False
    except ImportError:
        # Fallback to simple config class if pydantic not available
        BaseSettings = object
        Field = lambda default=None, **kwargs: default
        PYDANTIC_V2 = False
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    """Framework configuration settings"""
    
    # Framework
    framework_version: str = "3.0.0"
    debug_mode: bool = Field(default=False, env="NC_DEBUG")
    log_level: str = Field(default="INFO", env="NC_LOG_LEVEL")
    
    # API Keys
    claude_api_key: Optional[str] = Field(default=None, env="CLAUDE_API_KEY")
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    google_api_key: Optional[str] = Field(default=None, env="GOOGLE_API_KEY")
    github_token: Optional[str] = Field(default=None, env="GITHUB_TOKEN")
    brave_api_key: Optional[str] = Field(default=None, env="BRAVE_API_KEY")
    
    # Database
    database_url: str = Field(
        default="postgresql://nubemclaude:password@localhost:5432/nubemclaude",
        env="DATABASE_URL"
    )
    redis_url: str = Field(default="redis://localhost:6379", env="REDIS_URL")
    qdrant_url: str = Field(default="http://localhost:6333", env="QDRANT_URL")
    
    # Memory System
    memory_size: str = Field(default="10GB", env="NC_MEMORY_SIZE")
    cache_enabled: bool = Field(default=True, env="NC_CACHE_ENABLED")
    cache_ttl: int = Field(default=3600, env="NC_CACHE_TTL")
    
    # LLM Configuration
    default_model: str = Field(default="claude", env="NC_DEFAULT_MODEL")
    temperature: float = Field(default=0.7, env="NC_TEMPERATURE")
    max_tokens: int = Field(default=4096, env="NC_MAX_TOKENS")
    timeout: int = Field(default=30, env="NC_TIMEOUT")
    
    # Multi-LLM Orchestrator
    consensus_enabled: bool = Field(default=True, env="NC_CONSENSUS_ENABLED")
    consensus_threshold: float = Field(default=0.8, env="NC_CONSENSUS_THRESHOLD")
    consensus_models: list = Field(
        default=["claude", "gpt4", "gemini"],
        env="NC_CONSENSUS_MODELS"
    )
    
    # Quantum Features
    quantum_mode: bool = Field(default=False, env="NC_QUANTUM_MODE")
    quantum_algorithm: str = Field(default="grover", env="NC_QUANTUM_ALGORITHM")
    
    # Security
    jwt_secret: str = Field(default="change-me-in-production", env="JWT_SECRET")
    encryption_key: Optional[str] = Field(default=None, env="ENCRYPTION_KEY")
    api_rate_limit: int = Field(default=100, env="API_RATE_LIMIT")
    
    # Monitoring
    sentry_dsn: Optional[str] = Field(default=None, env="SENTRY_DSN")
    metrics_enabled: bool = Field(default=True, env="METRICS_ENABLED")
    
    # Paths
    data_dir: Path = Field(default=Path.home() / ".nubemclaude", env="NC_DATA_DIR")
    personas_dir: Path = Field(default=Path("./core"), env="NC_PERSONAS_DIR")
    knowledge_dir: Path = Field(default=Path("./knowledge"), env="NC_KNOWLEDGE_DIR")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    def __init__(self, config_path: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        
        if config_path:
            self.load_from_file(config_path)
        
        # Create directories if they don't exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "sessions").mkdir(exist_ok=True)
        (self.data_dir / "cache").mkdir(exist_ok=True)
        (self.data_dir / "logs").mkdir(exist_ok=True)
    
    def load_from_file(self, path: str):
        """Load configuration from JSON or YAML file"""
        path_obj = Path(path)
        
        if not path_obj.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        
        if path_obj.suffix == ".json":
            with open(path_obj, 'r') as f:
                config = json.load(f)
        elif path_obj.suffix in [".yml", ".yaml"]:
            import yaml
            with open(path_obj, 'r') as f:
                config = yaml.safe_load(f)
        else:
            raise ValueError(f"Unsupported config format: {path_obj.suffix}")
        
        # Update settings with loaded config
        for key, value in config.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    def validate_consensus_threshold(self):
        if not 0 <= self.consensus_threshold <= 1:
            raise ValueError("Consensus threshold must be between 0 and 1")
        return self.consensus_threshold
    
    def validate_temperature(self):
        if not 0 <= self.temperature <= 2:
            raise ValueError("Temperature must be between 0 and 2")
        return self.temperature
    
    def get_llm_config(self, model: str) -> Dict[str, Any]:
        """Get configuration for a specific LLM"""
        base_config = {
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            'timeout': self.timeout
        }
        
        if model == "claude":
            return {
                **base_config,
                'api_key': self.claude_api_key,
                'model': 'claude-3-opus-20240229'
            }
        elif model == "gpt4":
            return {
                **base_config,
                'api_key': self.openai_api_key,
                'model': 'gpt-4-turbo-preview'
            }
        elif model == "gemini":
            return {
                **base_config,
                'api_key': self.google_api_key,
                'model': 'gemini-1.5-pro'
            }
        else:
            return base_config
    
    def validate_api_keys(self) -> Dict[str, bool]:
        """Validate which API keys are configured"""
        return {
            'claude': bool(self.claude_api_key),
            'openai': bool(self.openai_api_key),
            'google': bool(self.google_api_key),
            'github': bool(self.github_token),
            'brave': bool(self.brave_api_key)
        }
    
    def export_safe_config(self) -> Dict[str, Any]:
        """Export configuration without sensitive data"""
        config = self.dict()
        
        # Remove sensitive fields
        sensitive_fields = [
            'claude_api_key', 'openai_api_key', 'google_api_key',
            'github_token', 'brave_api_key', 'jwt_secret',
            'encryption_key', 'sentry_dsn', 'database_url'
        ]
        
        for field in sensitive_fields:
            if field in config:
                config[field] = "***REDACTED***"
        
        return config
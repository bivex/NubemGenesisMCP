"""
Centralized configuration for NubemSuperFClaude
All settings in one place with environment variable support
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic import Field

# Try new pydantic-settings, fall back to legacy
try:
    from pydantic_settings import BaseSettings
except ImportError:
    try:
        from pydantic import BaseSettings
    except ImportError:
        # Fallback for Pydantic v2
        from pydantic.v1 import BaseSettings


class APISettings(BaseSettings):
    """API Keys and endpoints configuration"""

    # Anthropic
    anthropic_api_key: Optional[str] = Field(None, env='ANTHROPIC_API_KEY')
    anthropic_model: str = Field('claude-3-5-sonnet-20241022', env='ANTHROPIC_MODEL')

    # OpenAI
    openai_api_key: Optional[str] = Field(None, env='OPENAI_API_KEY')
    openai_model: str = Field('gpt-4-turbo-preview', env='OPENAI_MODEL')

    # Google
    gemini_api_key: Optional[str] = Field(None, env='GEMINI_API_KEY')
    gemini_model: str = Field('gemini-pro', env='GEMINI_MODEL')

    # Together
    together_api_key: Optional[str] = Field(None, env='TOGETHER_API_KEY')
    together_model: str = Field('meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo', env='TOGETHER_MODEL')

    # Groq
    groq_api_key: Optional[str] = Field(None, env='GROQ_API_KEY')
    groq_model: str = Field('llama-3.1-70b-versatile', env='GROQ_MODEL')

    class Config:
        env_file = '.env'
        extra = 'ignore'
        env_file_encoding = 'utf-8'
        extra = 'ignore'  # Ignore extra fields from .env


class DatabaseSettings(BaseSettings):
    """Database configuration"""
    
    # SQLite
    sqlite_path: str = Field('data/sessions.db', env='SQLITE_PATH')
    
    # Qdrant
    qdrant_host: str = Field('localhost', env='QDRANT_HOST')
    qdrant_port: int = Field(6333, env='QDRANT_PORT')
    qdrant_collection: str = Field('nubem_vectors', env='QDRANT_COLLECTION')
    
    # Redis (optional)
    redis_host: str = Field('localhost', env='REDIS_HOST')
    redis_port: int = Field(6379, env='REDIS_PORT')
    redis_db: int = Field(0, env='REDIS_DB')
    redis_password: Optional[str] = Field(None, env='REDIS_PASSWORD')
    
    class Config:
        env_file = '.env'
        extra = 'ignore'


class CacheSettings(BaseSettings):
    """Cache configuration"""
    
    cache_enabled: bool = Field(True, env='CACHE_ENABLED')
    cache_ttl: int = Field(3600, env='CACHE_TTL')  # seconds
    cache_dir: str = Field('.cache/nubem', env='CACHE_DIR')
    max_cache_size_mb: int = Field(500, env='MAX_CACHE_SIZE_MB')
    
    class Config:
        env_file = '.env'
        extra = 'ignore'


class OrchestrationSettings(BaseSettings):
    """Orchestration configuration"""
    
    default_strategy: str = Field('optimized', env='DEFAULT_STRATEGY')
    enable_personas: bool = Field(True, env='ENABLE_PERSONAS')
    enable_vector: bool = Field(False, env='ENABLE_VECTOR')
    enable_multi_llm: bool = Field(True, env='ENABLE_MULTI_LLM')
    max_retries: int = Field(3, env='MAX_RETRIES')
    timeout_seconds: int = Field(30, env='TIMEOUT_SECONDS')
    
    class Config:
        env_file = '.env'
        extra = 'ignore'


class LoggingSettings(BaseSettings):
    """Logging configuration"""
    
    log_level: str = Field('INFO', env='LOG_LEVEL')
    log_dir: str = Field('logs', env='LOG_DIR')
    log_format: str = Field('json', env='LOG_FORMAT')  # json or text
    log_rotation: str = Field('10MB', env='LOG_ROTATION')
    log_retention: int = Field(7, env='LOG_RETENTION')  # days
    
    class Config:
        env_file = '.env'
        extra = 'ignore'


class PerformanceSettings(BaseSettings):
    """Performance tuning"""
    
    max_workers: int = Field(4, env='MAX_WORKERS')
    batch_size: int = Field(32, env='BATCH_SIZE')
    embedding_model: str = Field('all-MiniLM-L6-v2', env='EMBEDDING_MODEL')
    embedding_dim: int = Field(384, env='EMBEDDING_DIM')
    max_memory_mb: int = Field(2048, env='MAX_MEMORY_MB')
    
    class Config:
        env_file = '.env'
        extra = 'ignore'


class Settings(BaseSettings):
    """Main settings aggregator"""
    
    # Sub-configurations
    api: APISettings = APISettings()
    database: DatabaseSettings = DatabaseSettings()
    cache: CacheSettings = CacheSettings()
    orchestration: OrchestrationSettings = OrchestrationSettings()
    logging: LoggingSettings = LoggingSettings()
    performance: PerformanceSettings = PerformanceSettings()
    
    # General settings
    project_name: str = Field('NubemSuperFClaude', env='PROJECT_NAME')
    version: str = Field('1.2.0', env='VERSION')
    environment: str = Field('development', env='ENVIRONMENT')
    debug: bool = Field(False, env='DEBUG')
    
    # Paths
    base_path: Path = Path(__file__).parent.parent
    data_path: Path = base_path / 'data'
    logs_path: Path = base_path / 'logs'
    cache_path: Path = base_path / '.cache'
    
    class Config:
        env_file = '.env'
        extra = 'ignore'
        env_file_encoding = 'utf-8'
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Create necessary directories
        self.data_path.mkdir(exist_ok=True)
        self.logs_path.mkdir(exist_ok=True)
        self.cache_path.mkdir(exist_ok=True)
    
    def get_api_keys(self) -> Dict[str, Optional[str]]:
        """Get all configured API keys"""
        return {
            'anthropic': self.api.anthropic_api_key,
            'openai': self.api.openai_api_key,
            'gemini': self.api.gemini_api_key,
            'together': self.api.together_api_key,
            'groq': self.api.groq_api_key
        }
    
    def get_available_providers(self) -> List[str]:
        """Get list of providers with configured API keys"""
        providers = []
        for provider, key in self.get_api_keys().items():
            if key:
                providers.append(provider)
        return providers
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary (excluding sensitive data)"""
        data = self.dict()
        # Remove API keys from export
        if 'api' in data:
            for key in data['api']:
                if 'api_key' in key:
                    data['api'][key] = '***' if data['api'][key] else None
        return data
    
    def validate_configuration(self) -> Dict[str, bool]:
        """Validate configuration completeness"""
        checks = {
            'has_llm_provider': len(self.get_available_providers()) > 0,
            'cache_dir_writable': os.access(self.cache_path, os.W_OK),
            'logs_dir_writable': os.access(self.logs_path, os.W_OK),
            'data_dir_writable': os.access(self.data_path, os.W_OK),
        }
        return checks


# Singleton instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get singleton settings instance"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# Export for convenience
settings = get_settings()


if __name__ == "__main__":
    # Test configuration
    s = get_settings()
    
    print("🔧 Configuration Status")
    print("=" * 50)
    
    print(f"Project: {s.project_name} v{s.version}")
    print(f"Environment: {s.environment}")
    print(f"Debug: {s.debug}")
    
    print("\n📊 API Providers:")
    providers = s.get_available_providers()
    if providers:
        for p in providers:
            print(f"  ✅ {p}")
    else:
        print("  ⚠️ No API providers configured")
    
    print("\n✅ Validation:")
    for check, passed in s.validate_configuration().items():
        status = "✅" if passed else "❌"
        print(f"  {status} {check}")
    
    print("\n📁 Paths:")
    print(f"  Base: {s.base_path}")
    print(f"  Data: {s.data_path}")
    print(f"  Logs: {s.logs_path}")
    print(f"  Cache: {s.cache_path}")
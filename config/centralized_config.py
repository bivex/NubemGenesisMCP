#!/usr/bin/env python3
"""
Centralized Configuration Management for NubemSuperFClaude
Consolida todas las configuraciones en un lugar para evitar duplicación
"""

import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class DatabaseConfig:
    """Configuración de base de datos"""
    url: str = "postgresql://nubemclaude:password@localhost:5432/nubemclaude"
    pool_size: int = 10
    pool_overflow: int = 20
    pool_timeout: int = 30
    pool_recycle: int = 3600


@dataclass 
class RedisConfig:
    """Configuración de Redis"""
    url: str = "redis://:nubemclaude2025@localhost:6379"
    password: str = "nubemclaude2025"
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    max_connections: int = 20
    socket_timeout: int = 30
    connection_timeout: int = 10


@dataclass
class QdrantConfig:
    """Configuración de Qdrant"""
    host: str = "localhost"
    port: int = 6333
    collection_name: str = "nubem_personas_semantic"
    api_key: Optional[str] = None
    timeout: int = 60
    # Connection pool settings
    min_connections: int = 2
    max_connections: int = 10
    max_idle_time_minutes: int = 30


@dataclass
class LLMConfig:
    """Configuración de LLMs"""
    claude_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    # Rate limiting
    max_requests_per_minute: int = 60
    max_tokens_per_request: int = 4000
    timeout_seconds: int = 30


@dataclass
class GCPConfig:
    """Configuración de Google Cloud Platform"""
    project_id: str = "nubemsuperfclaude"
    region: str = "us-central1"
    zone: str = "us-central1-a"
    credentials_path: str = "~/.config/gcloud/application_default_credentials.json"
    secret_manager_project: str = "nubemsecrets"


@dataclass
class CacheConfig:
    """Configuración de sistema de cache"""
    # L1 Cache (Memory)
    l1_max_size: int = 1000
    l1_max_memory_mb: int = 100
    # L2 Cache (Redis)
    l2_default_ttl: int = 3600
    # L3 Cache (Intelligent)
    l3_conversation_ttl: int = 1800  # 30 minutes
    l3_translation_ttl: int = 604800  # 7 days
    l3_creative_ttl: int = 0  # Never cache


@dataclass
class HealthCheckConfig:
    """Configuración de health checks"""
    redis_interval_seconds: int = 30
    qdrant_interval_seconds: int = 60
    cache_interval_seconds: int = 45
    timeout_seconds: int = 10
    max_history_size: int = 50


@dataclass
class SecurityConfig:
    """Configuración de seguridad"""
    allowed_origins: List[str] = field(default_factory=lambda: [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:8000",
        "https://*.nubemsuperfclaude.com"
    ])
    allowed_methods: List[str] = field(default_factory=lambda: [
        "GET", "POST", "PUT", "DELETE", "OPTIONS"
    ])
    allowed_headers: List[str] = field(default_factory=lambda: [
        "Authorization", "Content-Type", "X-Request-ID"
    ])
    max_request_size_mb: int = 10
    rate_limit_per_minute: int = 100


@dataclass
class MetricsConfig:
    """Configuración de métricas"""
    max_history_size: int = 10000
    cache_duration_seconds: int = 300  # 5 minutes
    enable_detailed_logging: bool = False
    retention_days: int = 30


@dataclass
class ServerConfig:
    """Configuración del servidor"""
    host: str = "0.0.0.0"
    port: int = 8080
    workers: int = 4
    debug: bool = False
    log_level: str = "INFO"
    reload: bool = False


class CentralizedConfig:
    """Configuración centralizada del sistema"""
    
    def __init__(self, env_file: Optional[str] = None):
        """Inicializar configuración desde variables de entorno"""
        if env_file and Path(env_file).exists():
            self._load_env_file(env_file)
        
        # Inicializar configuraciones
        self.database = self._init_database_config()
        self.redis = self._init_redis_config() 
        self.qdrant = self._init_qdrant_config()
        self.llm = self._init_llm_config()
        self.gcp = self._init_gcp_config()
        self.cache = self._init_cache_config()
        self.health_check = self._init_health_check_config()
        self.security = self._init_security_config()
        self.metrics = self._init_metrics_config()
        self.server = self._init_server_config()
        
        # Environment detection
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.is_production = self.environment == "production"
        self.is_development = self.environment == "development"
        
    def _load_env_file(self, env_file: str):
        """Cargar variables de entorno desde archivo"""
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
        except ImportError:
            logger.warning("python-dotenv not installed, skipping .env file loading")
    
    def _init_database_config(self) -> DatabaseConfig:
        """Inicializar configuración de base de datos"""
        return DatabaseConfig(
            url=os.getenv("DATABASE_URL", DatabaseConfig.url),
            pool_size=int(os.getenv("DB_POOL_SIZE", DatabaseConfig.pool_size)),
            pool_overflow=int(os.getenv("DB_POOL_OVERFLOW", DatabaseConfig.pool_overflow)),
            pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", DatabaseConfig.pool_timeout)),
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE", DatabaseConfig.pool_recycle))
        )
    
    def _init_redis_config(self) -> RedisConfig:
        """Inicializar configuración de Redis"""
        return RedisConfig(
            url=os.getenv("REDIS_URL", RedisConfig.url),
            password=os.getenv("REDIS_PASSWORD", RedisConfig.password),
            host=os.getenv("REDIS_HOST", RedisConfig.host),
            port=int(os.getenv("REDIS_PORT", RedisConfig.port)),
            db=int(os.getenv("REDIS_DB", RedisConfig.db)),
            max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", RedisConfig.max_connections)),
            socket_timeout=int(os.getenv("REDIS_SOCKET_TIMEOUT", RedisConfig.socket_timeout)),
            connection_timeout=int(os.getenv("REDIS_CONNECTION_TIMEOUT", RedisConfig.connection_timeout))
        )
    
    def _init_qdrant_config(self) -> QdrantConfig:
        """Inicializar configuración de Qdrant"""
        return QdrantConfig(
            host=os.getenv("QDRANT_HOST", QdrantConfig.host),
            port=int(os.getenv("QDRANT_PORT", QdrantConfig.port)),
            collection_name=os.getenv("QDRANT_COLLECTION", QdrantConfig.collection_name),
            api_key=os.getenv("QDRANT_API_KEY"),
            timeout=int(os.getenv("QDRANT_TIMEOUT", QdrantConfig.timeout)),
            min_connections=int(os.getenv("QDRANT_MIN_CONNECTIONS", QdrantConfig.min_connections)),
            max_connections=int(os.getenv("QDRANT_MAX_CONNECTIONS", QdrantConfig.max_connections)),
            max_idle_time_minutes=int(os.getenv("QDRANT_MAX_IDLE_TIME", QdrantConfig.max_idle_time_minutes))
        )
    
    def _init_llm_config(self) -> LLMConfig:
        """Inicializar configuración de LLMs"""
        return LLMConfig(
            claude_api_key=os.getenv("CLAUDE_API_KEY"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            gemini_api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY"),
            max_requests_per_minute=int(os.getenv("LLM_MAX_RPM", LLMConfig.max_requests_per_minute)),
            max_tokens_per_request=int(os.getenv("LLM_MAX_TOKENS", LLMConfig.max_tokens_per_request)),
            timeout_seconds=int(os.getenv("LLM_TIMEOUT", LLMConfig.timeout_seconds))
        )
    
    def _init_gcp_config(self) -> GCPConfig:
        """Inicializar configuración de GCP"""
        return GCPConfig(
            project_id=os.getenv("GCP_PROJECT", GCPConfig.project_id),
            region=os.getenv("GCP_REGION", GCPConfig.region),
            zone=os.getenv("GCP_ZONE", GCPConfig.zone),
            credentials_path=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", GCPConfig.credentials_path),
            secret_manager_project=os.getenv("SECRET_MANAGER_PROJECT", GCPConfig.secret_manager_project)
        )
    
    def _init_cache_config(self) -> CacheConfig:
        """Inicializar configuración de cache"""
        return CacheConfig(
            l1_max_size=int(os.getenv("CACHE_L1_MAX_SIZE", CacheConfig.l1_max_size)),
            l1_max_memory_mb=int(os.getenv("CACHE_L1_MAX_MEMORY_MB", CacheConfig.l1_max_memory_mb)),
            l2_default_ttl=int(os.getenv("CACHE_L2_DEFAULT_TTL", CacheConfig.l2_default_ttl)),
            l3_conversation_ttl=int(os.getenv("CACHE_L3_CONVERSATION_TTL", CacheConfig.l3_conversation_ttl)),
            l3_translation_ttl=int(os.getenv("CACHE_L3_TRANSLATION_TTL", CacheConfig.l3_translation_ttl)),
            l3_creative_ttl=int(os.getenv("CACHE_L3_CREATIVE_TTL", CacheConfig.l3_creative_ttl))
        )
    
    def _init_health_check_config(self) -> HealthCheckConfig:
        """Inicializar configuración de health checks"""
        return HealthCheckConfig(
            redis_interval_seconds=int(os.getenv("HEALTH_REDIS_INTERVAL", HealthCheckConfig.redis_interval_seconds)),
            qdrant_interval_seconds=int(os.getenv("HEALTH_QDRANT_INTERVAL", HealthCheckConfig.qdrant_interval_seconds)),
            cache_interval_seconds=int(os.getenv("HEALTH_CACHE_INTERVAL", HealthCheckConfig.cache_interval_seconds)),
            timeout_seconds=int(os.getenv("HEALTH_TIMEOUT", HealthCheckConfig.timeout_seconds)),
            max_history_size=int(os.getenv("HEALTH_MAX_HISTORY", HealthCheckConfig.max_history_size))
        )
    
    def _init_security_config(self) -> SecurityConfig:
        """Inicializar configuración de seguridad"""
        # Parse allowed origins from env
        allowed_origins = os.getenv("ALLOWED_ORIGINS")
        if allowed_origins:
            origins_list = [origin.strip() for origin in allowed_origins.split(",")]
        else:
            origins_list = [
                "http://localhost:3000",
                "http://localhost:8080",
                "http://localhost:8000",
                "https://*.nubemsuperfclaude.com"
            ]
        
        return SecurityConfig(
            allowed_origins=origins_list,
            max_request_size_mb=int(os.getenv("MAX_REQUEST_SIZE_MB", "10")),
            rate_limit_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "100"))
        )
    
    def _init_metrics_config(self) -> MetricsConfig:
        """Inicializar configuración de métricas"""
        return MetricsConfig(
            max_history_size=int(os.getenv("METRICS_MAX_HISTORY", MetricsConfig.max_history_size)),
            cache_duration_seconds=int(os.getenv("METRICS_CACHE_DURATION", MetricsConfig.cache_duration_seconds)),
            enable_detailed_logging=os.getenv("METRICS_DETAILED_LOGGING", "false").lower() == "true",
            retention_days=int(os.getenv("METRICS_RETENTION_DAYS", MetricsConfig.retention_days))
        )
    
    def _init_server_config(self) -> ServerConfig:
        """Inicializar configuración del servidor"""
        return ServerConfig(
            host=os.getenv("HOST", ServerConfig.host),
            port=int(os.getenv("PORT", ServerConfig.port)),
            workers=int(os.getenv("WORKERS", ServerConfig.workers)),
            debug=os.getenv("DEBUG", "false").lower() == "true",
            log_level=os.getenv("LOG_LEVEL", ServerConfig.log_level),
            reload=os.getenv("RELOAD", "false").lower() == "true"
        )
    
    def get_all_config(self) -> Dict[str, Any]:
        """Obtener toda la configuración como diccionario"""
        return {
            "environment": self.environment,
            "database": self.database.__dict__,
            "redis": self.redis.__dict__, 
            "qdrant": self.qdrant.__dict__,
            "llm": {
                **self.llm.__dict__,
                # Mask sensitive keys
                "claude_api_key": "***" if self.llm.claude_api_key else None,
                "openai_api_key": "***" if self.llm.openai_api_key else None,
                "gemini_api_key": "***" if self.llm.gemini_api_key else None,
                "anthropic_api_key": "***" if self.llm.anthropic_api_key else None,
            },
            "gcp": {
                **self.gcp.__dict__,
                "credentials_path": "***" if self.gcp.credentials_path else None
            },
            "cache": self.cache.__dict__,
            "health_check": self.health_check.__dict__,
            "security": self.security.__dict__,
            "metrics": self.metrics.__dict__,
            "server": self.server.__dict__
        }
    
    def validate_config(self) -> List[str]:
        """Validar configuración y retornar lista de errores"""
        errors = []
        
        # Validar configuraciones críticas
        if not self.llm.claude_api_key and not self.llm.openai_api_key:
            errors.append("At least one LLM API key (Claude or OpenAI) is required")
        
        if self.redis.password == "nubemclaude2025" and self.is_production:
            errors.append("Default Redis password should not be used in production")
        
        if self.server.debug and self.is_production:
            errors.append("Debug mode should not be enabled in production")
        
        try:
            if not Path(self.gcp.credentials_path).expanduser().exists():
                errors.append(f"GCP credentials file not found: {self.gcp.credentials_path}")
        except Exception:
            # Skip GCP validation if path is invalid
            pass
        
        return errors


# Singleton instance
_config: Optional[CentralizedConfig] = None


def get_config(reload: bool = False) -> CentralizedConfig:
    """Obtener instancia singleton de la configuración"""
    global _config
    
    if _config is None or reload:
        env_file = None
        # Try to find .env file
        for env_path in [".env", ".env.local", "../.env"]:
            if Path(env_path).exists():
                env_file = env_path
                break
        
        _config = CentralizedConfig(env_file=env_file)
        
        # Validate configuration
        errors = _config.validate_config()
        if errors:
            logger.warning(f"Configuration validation errors: {errors}")
    
    return _config


def get_database_config() -> DatabaseConfig:
    """Obtener configuración de base de datos"""
    return get_config().database


def get_redis_config() -> RedisConfig:
    """Obtener configuración de Redis"""
    return get_config().redis


def get_qdrant_config() -> QdrantConfig:
    """Obtener configuración de Qdrant"""
    return get_config().qdrant


def get_llm_config() -> LLMConfig:
    """Obtener configuración de LLMs"""
    return get_config().llm


def get_gcp_config() -> GCPConfig:
    """Obtener configuración de GCP"""
    return get_config().gcp


def get_cache_config() -> CacheConfig:
    """Obtener configuración de cache"""
    return get_config().cache


def get_health_check_config() -> HealthCheckConfig:
    """Obtener configuración de health checks"""
    return get_config().health_check


def get_security_config() -> SecurityConfig:
    """Obtener configuración de seguridad"""
    return get_config().security


def get_metrics_config() -> MetricsConfig:
    """Obtener configuración de métricas"""
    return get_config().metrics


def get_server_config() -> ServerConfig:
    """Obtener configuración del servidor"""
    return get_config().server
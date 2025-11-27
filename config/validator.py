"""
Configuration Validator for NubemSuperFClaude
Validates all environment variables and configuration settings
"""

from typing import Optional, Dict, Any
from pydantic_settings import BaseSettings
from pydantic import validator, Field
import os
from pathlib import Path


class Settings(BaseSettings):
    """Main configuration settings with validation"""
    
    # API Keys
    OPENAI_API_KEY: Optional[str] = Field(None, description="OpenAI API key")
    ANTHROPIC_API_KEY: Optional[str] = Field(None, description="Anthropic Claude API key")
    CLAUDE_API_KEY: Optional[str] = Field(None, description="Alias for Anthropic API key")
    GEMINI_API_KEY: Optional[str] = Field(None, description="Google Gemini API key")
    GOOGLE_API_KEY: Optional[str] = Field(None, description="Google API key")
    GROQ_API_KEY: Optional[str] = Field(None, description="Groq API key")
    
    # Google Cloud Platform
    GCP_PROJECT: Optional[str] = Field(None, description="GCP Project ID")
    GCP_REGION: str = Field("us-central1", description="GCP Region")
    GCP_ZONE: Optional[str] = Field("us-central1-a", description="GCP Zone")
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
    GOOGLE_CLOUD_PROJECT: Optional[str] = Field(None, description="Alias for GCP_PROJECT")
    
    # Database Configuration
    REDIS_URL: str = Field("redis://localhost:6379/0", description="Redis connection URL")
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "nubemsuper"
    POSTGRES_USER: str = "nubem"
    POSTGRES_PASSWORD: str = ""
    
    # Vector Database
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_COLLECTION: str = "nubem_vectors"
    
    # Security
    SECRET_KEY: str = Field(..., description="Application secret key")
    JWT_SECRET_KEY: str = Field(..., description="JWT secret key")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    API_KEY_ROTATION_DAYS: int = 90
    
    # Performance
    MAX_WORKERS: int = 10
    BATCH_SIZE: int = 32
    CONNECTION_POOL_SIZE: int = 20
    REQUEST_TIMEOUT: int = 30
    CACHE_TTL: int = 3600  # 1 hour
    
    # Framework Configuration
    NC_MEMORY_SIZE: str = "100GB"
    NC_CACHE_ENABLED: bool = True
    NC_QUANTUM_MODE: bool = False
    NC_CONSENSUS_THRESHOLD: float = 0.85
    NC_DEFAULT_PERSONA: str = "full-stack-architect"
    NC_AUTO_OPTIMIZE: bool = True
    NC_LEARNING_RATE: float = 0.03
    
    # API Configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    WEBSOCKET_PORT: int = 8001
    GRAPHQL_PORT: int = 8002
    
    # Monitoring
    PROMETHEUS_ENABLED: bool = True
    PROMETHEUS_PORT: int = 9090
    SENTRY_DSN: Optional[str] = None
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    
    # Environment
    DEBUG: bool = False
    TESTING: bool = False
    ENVIRONMENT: str = "development"
    ENV: Optional[str] = Field("development", description="Alias for ENVIRONMENT")
    HOST: str = Field("127.0.0.1", description="Server host")
    PORT: int = Field(8001, description="Server port")
    
    # Feature Flags
    ENABLE_VECTOR_SEARCH: bool = True
    ENABLE_API_ROTATION: bool = True
    ENABLE_MULTI_LLM: bool = True
    ENABLE_QUANTUM_ALGORITHMS: bool = False
    ENABLE_AUTO_SCALING: bool = True
    ENABLE_REDIS: bool = True
    ENABLE_VECTOR_DB: bool = True
    ENABLE_MONITORING: bool = False
    ENABLE_CACHING: bool = True
    
    # Additional fields
    JWT_SECRET: Optional[str] = Field(None, description="JWT Secret")
    ENCRYPTION_KEY: Optional[str] = Field(None, description="Encryption key")
    SESSION_SECRET: Optional[str] = Field(None, description="Session secret")
    DATABASE_URL: Optional[str] = Field(None, description="Database URL")
    LOG_FILE_PATH: Optional[str] = Field("./logs/app.log", description="Log file path")
    CACHE_DIR: Optional[str] = Field("./cache", description="Cache directory")
    DATA_DIR: Optional[str] = Field("./data", description="Data directory")
    WORKERS: int = Field(1, description="Number of workers")
    RELOAD: bool = Field(False, description="Auto-reload on changes")
    
    @validator("OPENAI_API_KEY")
    def validate_openai_key(cls, v):
        if v and not v.startswith("sk-"):
            raise ValueError("Invalid OpenAI API key format")
        return v
    
    @validator("ANTHROPIC_API_KEY")
    def validate_anthropic_key(cls, v):
        if v and not v.startswith("sk-ant-"):
            raise ValueError("Invalid Anthropic API key format")
        return v
    
    @validator("GEMINI_API_KEY")
    def validate_gemini_key(cls, v):
        if v and not v.startswith("AI"):
            raise ValueError("Invalid Gemini API key format")
        return v
    
    @validator("SECRET_KEY", "JWT_SECRET_KEY")
    def validate_secret_keys(cls, v):
        if len(v) < 32:
            raise ValueError("Secret keys must be at least 32 characters long")
        return v
    
    @validator("NC_CONSENSUS_THRESHOLD")
    def validate_consensus_threshold(cls, v):
        if not 0 <= v <= 1:
            raise ValueError("Consensus threshold must be between 0 and 1")
        return v
    
    @validator("ENVIRONMENT")
    def validate_environment(cls, v):
        valid_envs = ["development", "staging", "production", "testing"]
        if v not in valid_envs:
            raise ValueError(f"Environment must be one of {valid_envs}")
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "allow"  # Allow extra fields from .env


class ConfigValidator:
    """Validates and manages configuration"""
    
    def __init__(self):
        self.settings = None
        self.errors = []
        self.warnings = []
    
    def validate(self) -> bool:
        """Validate all configuration settings"""
        try:
            self.settings = Settings()
            self._check_api_keys()
            self._check_database_connections()
            self._check_security_settings()
            return len(self.errors) == 0
        except Exception as e:
            self.errors.append(f"Configuration validation failed: {str(e)}")
            return False
    
    def _check_api_keys(self):
        """Check if at least one LLM API key is configured"""
        llm_keys = [
            self.settings.OPENAI_API_KEY,
            self.settings.ANTHROPIC_API_KEY,
            self.settings.GEMINI_API_KEY
        ]
        
        if not any(llm_keys):
            self.warnings.append("No LLM API keys configured. At least one is recommended.")
        
        # Check for GCP credentials if GCP features are enabled
        if self.settings.GCP_PROJECT and not self.settings.GOOGLE_APPLICATION_CREDENTIALS:
            self.warnings.append("GCP_PROJECT set but GOOGLE_APPLICATION_CREDENTIALS not configured")
    
    def _check_database_connections(self):
        """Validate database configuration"""
        # Check PostgreSQL settings
        if not self.settings.POSTGRES_PASSWORD:
            self.warnings.append("PostgreSQL password not set")
        
        # Check Redis URL format
        if not self.settings.REDIS_URL.startswith("redis://"):
            self.errors.append("Invalid Redis URL format")
    
    def _check_security_settings(self):
        """Validate security configuration"""
        # Check if using default secret keys
        if self.settings.SECRET_KEY == "your-secret-key-here-change-this":
            self.errors.append("Using default SECRET_KEY. Please change it!")
        
        if self.settings.JWT_SECRET_KEY == "your-jwt-secret-here-change-this":
            self.errors.append("Using default JWT_SECRET_KEY. Please change it!")
        
        # Warn about debug mode in production
        if self.settings.ENVIRONMENT == "production" and self.settings.DEBUG:
            self.warnings.append("DEBUG mode enabled in production environment!")
    
    def get_report(self) -> Dict[str, Any]:
        """Get validation report"""
        return {
            "valid": len(self.errors) == 0,
            "errors": self.errors,
            "warnings": self.warnings,
            "environment": self.settings.ENVIRONMENT if self.settings else "unknown",
            "features": {
                "vector_search": self.settings.ENABLE_VECTOR_SEARCH if self.settings else False,
                "api_rotation": self.settings.ENABLE_API_ROTATION if self.settings else False,
                "multi_llm": self.settings.ENABLE_MULTI_LLM if self.settings else False,
            } if self.settings else {}
        }
    
    def print_report(self):
        """Print validation report to console"""
        report = self.get_report()
        
        print("\n" + "="*60)
        print("NubemSuperFClaude Configuration Validation Report")
        print("="*60)
        
        if report["valid"]:
            print("✅ Configuration is valid")
        else:
            print("❌ Configuration has errors")
        
        print(f"\nEnvironment: {report['environment']}")
        
        if report["errors"]:
            print("\n🚨 Errors:")
            for error in report["errors"]:
                print(f"  - {error}")
        
        if report["warnings"]:
            print("\n⚠️  Warnings:")
            for warning in report["warnings"]:
                print(f"  - {warning}")
        
        print("\n📊 Features Enabled:")
        for feature, enabled in report["features"].items():
            status = "✅" if enabled else "❌"
            print(f"  {status} {feature}")
        
        print("="*60 + "\n")


def get_settings() -> Settings:
    """Get validated settings singleton"""
    return Settings()


if __name__ == "__main__":
    # Run validation when executed directly
    validator = ConfigValidator()
    if validator.validate():
        validator.print_report()
        print("Configuration loaded successfully!")
    else:
        validator.print_report()
        exit(1)
#!/usr/bin/env python3
"""
NubemSuperFClaude - Secrets Loader
Loads secrets from Google Secret Manager and sets them as environment variables
This ensures all scripts can access secrets without modification
"""

import os
import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.secrets_manager import secrets_manager

logger = logging.getLogger(__name__)

def load_secrets_to_env():
    """
    Load secrets from Google Secret Manager and set as environment variables
    This allows existing code to work without modification
    """
    
    # Secret name to environment variable mapping
    secret_mappings = {
        'openai-api-key': ['OPENAI_API_KEY', 'OPENAI_KEY'],
        'anthropic-api-key': ['ANTHROPIC_API_KEY', 'CLAUDE_API_KEY'],
        'gemini-api-key': ['GEMINI_API_KEY', 'GOOGLE_API_KEY', 'GOOGLE_GEMINI_KEY'],
        'huggingface-api-token': ['HUGGINGFACE_TOKEN', 'HUGGINGFACE_API_KEY', 'HF_TOKEN'],
        'jwt-secret': ['JWT_SECRET', 'JWT_SECRET_KEY'],
        'session-secret': ['SESSION_SECRET', 'SESSION_SECRET_KEY'],
        'github-token': ['GITHUB_TOKEN'],
        'replicate-api-token': ['REPLICATE_API_TOKEN'],
        'stability-api-key': ['STABILITY_API_KEY'],
        'brave-api-key': ['BRAVE_API_KEY']
    }
    
    loaded_secrets = 0
    
    for secret_name, env_vars in secret_mappings.items():
        secret_value = secrets_manager.get_secret(secret_name)
        
        if secret_value:
            # Set primary environment variable
            primary_env_var = env_vars[0]
            
            # Only set if not already defined (allow override)
            if not os.getenv(primary_env_var):
                os.environ[primary_env_var] = secret_value
                loaded_secrets += 1
                logger.debug(f"Loaded {secret_name} as {primary_env_var}")
            
            # Also set alternative names if they don't exist
            for env_var in env_vars[1:]:
                if not os.getenv(env_var):
                    os.environ[env_var] = secret_value
    
    # Show configuration info if debug enabled
    if os.getenv('NC_DEBUG', '').lower() == 'true':
        config_info = secrets_manager.get_configuration_info()
        print(f"🔐 Secrets Manager Configuration:")
        print(f"  Secret Manager enabled: {config_info['secret_manager_enabled']}")
        print(f"  Google Cloud available: {config_info['google_cloud_available']}")
        print(f"  Project ID: {config_info['project_id']}")
        print(f"  Client initialized: {config_info['client_initialized']}")
        print(f"  Loaded secrets: {loaded_secrets}")
    
    return loaded_secrets

def validate_secrets():
    """Validate that required secrets are available"""
    validation_results = secrets_manager.validate_required_secrets()
    
    # Check for critical secrets
    critical_secrets = ['openai-api-key', 'anthropic-api-key']
    available_critical = sum(1 for secret in critical_secrets 
                           if validation_results.get(secret, False))
    
    if available_critical < 1:
        logger.warning("No critical AI API keys available - some features may not work")
        return False
    
    return True

def initialize_secrets():
    """Initialize secrets loading - call this early in application startup"""
    try:
        loaded_count = load_secrets_to_env()
        is_valid = validate_secrets()
        
        if loaded_count > 0:
            logger.info(f"Loaded {loaded_count} secrets from Secret Manager")
        
        return is_valid
        
    except Exception as e:
        logger.error(f"Failed to initialize secrets: {e}")
        logger.info("Continuing with environment variables only")
        return False

# Auto-initialize when imported (unless disabled)
if __name__ != "__main__" and os.getenv('NC_SKIP_AUTO_SECRETS', '').lower() != 'true':
    initialize_secrets()

if __name__ == "__main__":
    # Test the secrets loader
    print("🔐 Testing NubemSuperFClaude Secrets Loader")
    print("=" * 50)
    
    # Initialize
    success = initialize_secrets()
    
    # Show status
    print(f"\n🎯 Secrets Loading: {'✅ Success' if success else '⚠️  Partial/Failed'}")
    
    # Show available keys (redacted)
    available_keys = []
    test_keys = ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'HUGGINGFACE_API_KEY']
    
    for key in test_keys:
        value = os.getenv(key)
        if value:
            redacted = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
            available_keys.append(f"  ✅ {key}: {redacted}")
        else:
            available_keys.append(f"  ❌ {key}: Not available")
    
    print("\n🔑 Available API Keys:")
    for key_info in available_keys:
        print(key_info)
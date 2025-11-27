#!/usr/bin/env python3
"""
Configuration loader for NubemSuperFClaude
Loads project-specific settings from .nubemclaude.yml
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List

class ConfigLoader:
    """Loads and manages project configuration"""
    
    def __init__(self, config_file: str = None):
        """
        Initialize configuration loader
        
        Args:
            config_file: Path to configuration file
        """
        self.config_file = Path(config_file or self._find_config_file())
        self.config = self._load_config()
        self._apply_to_environment()
    
    def _find_config_file(self) -> Path:
        """Find configuration file in current or parent directories"""
        current = Path.cwd()
        
        # Check current directory and parents
        for directory in [current] + list(current.parents):
            config_path = directory / '.nubemclaude.yml'
            if config_path.exists():
                return config_path
        
        # Default to home directory config
        home_config = Path.home() / 'NubemSuperFClaude' / '.nubemclaude.yml'
        if home_config.exists():
            return home_config
        
        # Return default path even if it doesn't exist
        return Path.cwd() / '.nubemclaude.yml'
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        if not self.config_file.exists():
            return self._get_default_config()
        
        try:
            with open(self.config_file, 'r') as f:
                config = yaml.safe_load(f) or {}
                
            # Merge with defaults
            default_config = self._get_default_config()
            return self._deep_merge(default_config, config)
        except Exception as e:
            print(f"Warning: Could not load config from {self.config_file}: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            'multi_llm': {
                'enabled': True,
                'default_models': ['claude', 'openai'],
                'timeout': 30,
                'cache': {
                    'enabled': True,
                    'ttl': 300,
                    'directory': '~/.nubem_cache/llm_responses'
                },
                'presets': {
                    'fast': {
                        'name': 'Fast (Claude + GPT-4)',
                        'models': ['claude', 'openai']
                    },
                    'complete': {
                        'name': 'Complete (All available)',
                        'models': ['claude', 'openai', 'llama', 'gemini', 'groq', 'mistral', 'perplexity']
                    }
                }
            },
            'debug': {
                'enabled': False,
                'log_level': 'INFO',
                'log_file': 'logs/multi_llm.log'
            },
            'response': {
                'max_display_length': 500,
                'save_full_responses': True,
                'export_format': 'markdown'
            },
            'metrics': {
                'track_usage': True,
                'show_response_times': True,
                'show_token_counts': True
            }
        }
    
    def _deep_merge(self, base: Dict, update: Dict) -> Dict:
        """Deep merge two dictionaries"""
        result = base.copy()
        
        for key, value in update.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def _apply_to_environment(self):
        """Apply configuration to environment variables"""
        # Multi-LLM settings
        if self.config.get('multi_llm', {}).get('enabled'):
            models = self.config['multi_llm'].get('default_models', [])
            if isinstance(models, list):
                os.environ['NUBEM_DEFAULT_MODELS'] = ','.join(models)
            
            os.environ['NUBEM_LLM_TIMEOUT'] = str(self.config['multi_llm'].get('timeout', 30))
            
            # Cache settings
            cache_config = self.config['multi_llm'].get('cache', {})
            if cache_config.get('enabled'):
                os.environ['NUBEM_CACHE_TTL'] = str(cache_config.get('ttl', 300))
        
        # Debug settings
        debug_config = self.config.get('debug', {})
        if debug_config.get('enabled'):
            os.environ['NUBEM_DEBUG'] = 'true'
        
        # API keys (only if specified)
        api_keys = self.config.get('api_keys', {})
        for provider, key in api_keys.items():
            if key:  # Only override if key is provided
                env_var = f"{provider.upper()}_API_KEY"
                if provider == 'gemini':
                    env_var = 'GOOGLE_GEMINI_KEY'
                os.environ[env_var] = key
    
    def get(self, path: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-separated path
        
        Args:
            path: Dot-separated path (e.g., 'multi_llm.timeout')
            default: Default value if path not found
        
        Returns:
            Configuration value or default
        """
        keys = path.split('.')
        value = self.config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def get_preset(self, preset_name: str) -> Optional[Dict[str, Any]]:
        """Get preset configuration by name"""
        presets = self.get('multi_llm.presets', {})
        return presets.get(preset_name)
    
    def get_models_for_preset(self, preset_name: str) -> List[str]:
        """Get model list for a specific preset"""
        preset = self.get_preset(preset_name)
        if preset:
            return preset.get('models', [])
        return []
    
    def is_multi_llm_enabled(self) -> bool:
        """Check if multi-LLM verification is enabled"""
        return self.get('multi_llm.enabled', True)
    
    def get_cache_settings(self) -> Dict[str, Any]:
        """Get cache configuration"""
        return self.get('multi_llm.cache', {})
    
    def get_debug_settings(self) -> Dict[str, Any]:
        """Get debug configuration"""
        return self.get('debug', {})
    
    def save(self, config_file: str = None):
        """Save current configuration to file"""
        save_path = Path(config_file or self.config_file)
        
        try:
            with open(save_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False


# Singleton instance
_config_instance = None

def get_config() -> ConfigLoader:
    """Get or create configuration instance"""
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigLoader()
    return _config_instance


if __name__ == "__main__":
    # Test configuration loader
    config = get_config()
    
    print("Configuration loaded from:", config.config_file)
    print("\nMulti-LLM settings:")
    print(f"  Enabled: {config.is_multi_llm_enabled()}")
    print(f"  Default models: {config.get('multi_llm.default_models')}")
    print(f"  Timeout: {config.get('multi_llm.timeout')}s")
    print(f"\nCache settings:")
    print(f"  {config.get_cache_settings()}")
    print(f"\nDebug settings:")
    print(f"  {config.get_debug_settings()}")
    print(f"\nPresets:")
    for preset_name in config.get('multi_llm.presets', {}).keys():
        models = config.get_models_for_preset(preset_name)
        print(f"  {preset_name}: {models}")
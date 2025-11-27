#!/usr/bin/env python3
"""
Dynamic Plugin System for NubemSuperFClaude
Allows safe loading and unloading of external plugins
"""

import os
import sys
import importlib
import importlib.util
import inspect
import asyncio
import json
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
import logging
import hashlib

logger = logging.getLogger(__name__)

@dataclass
class PluginMetadata:
    """Metadata for a plugin"""
    name: str
    version: str
    author: str
    description: str
    dependencies: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    entry_point: str = "main"
    api_version: str = "2.0"
    tags: List[str] = field(default_factory=list)

@dataclass
class PluginInfo:
    """Complete plugin information"""
    id: str
    metadata: PluginMetadata
    path: Path
    module: Optional[Any] = None
    instance: Optional[Any] = None
    loaded: bool = False
    enabled: bool = True
    load_time: Optional[datetime] = None
    error: Optional[str] = None
    checksum: str = ""

class PluginBase:
    """Base class for all plugins"""
    
    def __init__(self, context: Dict[str, Any]):
        self.context = context
        self.logger = logging.getLogger(f"plugin.{self.__class__.__name__}")
    
    async def initialize(self) -> bool:
        """Initialize the plugin"""
        return True
    
    async def execute(self, *args, **kwargs) -> Any:
        """Execute plugin functionality"""
        raise NotImplementedError
    
    async def cleanup(self) -> None:
        """Cleanup resources"""
        pass
    
    def get_commands(self) -> Dict[str, Callable]:
        """Get available commands"""
        return {}
    
    def get_hooks(self) -> Dict[str, Callable]:
        """Get event hooks"""
        return {}

class PluginSandbox:
    """Sandbox environment for plugin execution"""
    
    def __init__(self, plugin_id: str):
        self.plugin_id = plugin_id
        self.restricted_modules = [
            'os', 'sys', 'subprocess', '__builtins__'
        ]
        self.allowed_imports = [
            'json', 'datetime', 'math', 'random', 
            'collections', 'itertools', 'functools'
        ]
    
    def validate_code(self, code: str) -> bool:
        """Validate plugin code for security"""
        # Check for dangerous operations
        dangerous_patterns = [
            'exec', 'eval', '__import__', 'compile',
            'open', 'file', 'input', 'raw_input'
        ]
        
        for pattern in dangerous_patterns:
            if pattern in code:
                logger.warning(f"Plugin {self.plugin_id} contains dangerous pattern: {pattern}")
                return False
        
        return True
    
    def create_restricted_globals(self) -> Dict[str, Any]:
        """Create restricted global namespace"""
        safe_builtins = {
            'abs': abs, 'all': all, 'any': any, 'bool': bool,
            'dict': dict, 'enumerate': enumerate, 'filter': filter,
            'float': float, 'int': int, 'len': len, 'list': list,
            'map': map, 'max': max, 'min': min, 'range': range,
            'round': round, 'set': set, 'sorted': sorted, 'str': str,
            'sum': sum, 'tuple': tuple, 'type': type, 'zip': zip
        }
        
        return {
            '__builtins__': safe_builtins,
            '__name__': f'plugin_{self.plugin_id}',
            '__doc__': None
        }

class DynamicPluginManager:
    """Manager for dynamic plugin loading and execution"""
    
    def __init__(self, plugins_dir: str = "plugins"):
        self.plugins_dir = Path(plugins_dir)
        self.plugins_dir.mkdir(exist_ok=True)
        
        self.plugins: Dict[str, PluginInfo] = {}
        self.hooks: Dict[str, List[Callable]] = {}
        self.commands: Dict[str, Callable] = {}
        self._lock = asyncio.Lock()
        
        # Plugin directories
        self.system_plugins_dir = self.plugins_dir / "system"
        self.user_plugins_dir = self.plugins_dir / "user"
        self.community_plugins_dir = self.plugins_dir / "community"
        
        for dir in [self.system_plugins_dir, self.user_plugins_dir, self.community_plugins_dir]:
            dir.mkdir(exist_ok=True)
    
    async def discover_plugins(self) -> List[PluginInfo]:
        """Discover available plugins"""
        discovered = []
        
        # Search in all plugin directories
        for plugins_root in [self.system_plugins_dir, self.user_plugins_dir, self.community_plugins_dir]:
            for plugin_dir in plugins_root.iterdir():
                if plugin_dir.is_dir():
                    manifest_path = plugin_dir / "manifest.json"
                    if manifest_path.exists():
                        try:
                            plugin_info = await self._load_manifest(plugin_dir)
                            if plugin_info:
                                discovered.append(plugin_info)
                        except Exception as e:
                            logger.error(f"Error loading manifest from {plugin_dir}: {e}")
        
        logger.info(f"Discovered {len(discovered)} plugins")
        return discovered
    
    async def _load_manifest(self, plugin_dir: Path) -> Optional[PluginInfo]:
        """Load plugin manifest"""
        manifest_path = plugin_dir / "manifest.json"
        
        try:
            with open(manifest_path, 'r') as f:
                manifest_data = json.load(f)
            
            metadata = PluginMetadata(**manifest_data)
            
            # Generate plugin ID
            plugin_id = f"{metadata.name}_{metadata.version}".replace('.', '_')
            
            # Calculate checksum
            plugin_file = plugin_dir / f"{metadata.entry_point}.py"
            if plugin_file.exists():
                with open(plugin_file, 'rb') as f:
                    checksum = hashlib.sha256(f.read()).hexdigest()
            else:
                checksum = ""
            
            return PluginInfo(
                id=plugin_id,
                metadata=metadata,
                path=plugin_dir,
                checksum=checksum
            )
            
        except Exception as e:
            logger.error(f"Failed to load manifest from {plugin_dir}: {e}")
            return None
    
    async def load_plugin(self, plugin_id: str) -> bool:
        """Load a plugin"""
        async with self._lock:
            if plugin_id in self.plugins and self.plugins[plugin_id].loaded:
                logger.info(f"Plugin {plugin_id} already loaded")
                return True
            
            # Find plugin info
            plugin_info = None
            discovered = await self.discover_plugins()
            for info in discovered:
                if info.id == plugin_id:
                    plugin_info = info
                    break
            
            if not plugin_info:
                logger.error(f"Plugin {plugin_id} not found")
                return False
            
            try:
                # Create sandbox
                sandbox = PluginSandbox(plugin_id)
                
                # Load plugin module
                plugin_file = plugin_info.path / f"{plugin_info.metadata.entry_point}.py"
                
                if not plugin_file.exists():
                    raise FileNotFoundError(f"Plugin file not found: {plugin_file}")
                
                # Validate code
                with open(plugin_file, 'r') as f:
                    code = f.read()
                
                if not sandbox.validate_code(code):
                    raise SecurityError(f"Plugin {plugin_id} failed security validation")
                
                # Load module
                spec = importlib.util.spec_from_file_location(
                    f"plugin_{plugin_id}",
                    plugin_file
                )
                
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    
                    # Add to sys.modules temporarily
                    sys.modules[f"plugin_{plugin_id}"] = module
                    
                    # Execute module
                    spec.loader.exec_module(module)
                    
                    plugin_info.module = module
                    
                    # Find and instantiate plugin class
                    plugin_class = None
                    for name, obj in inspect.getmembers(module):
                        if inspect.isclass(obj) and issubclass(obj, PluginBase) and obj != PluginBase:
                            plugin_class = obj
                            break
                    
                    if not plugin_class:
                        raise ValueError(f"No plugin class found in {plugin_id}")
                    
                    # Create plugin instance
                    context = {
                        'plugin_id': plugin_id,
                        'plugin_dir': str(plugin_info.path),
                        'manager': self
                    }
                    
                    plugin_info.instance = plugin_class(context)
                    
                    # Initialize plugin
                    if await plugin_info.instance.initialize():
                        plugin_info.loaded = True
                        plugin_info.load_time = datetime.now()
                        
                        # Register commands and hooks
                        self._register_plugin_features(plugin_id, plugin_info.instance)
                        
                        self.plugins[plugin_id] = plugin_info
                        
                        logger.info(f"Plugin {plugin_id} loaded successfully")
                        return True
                    else:
                        raise RuntimeError(f"Plugin {plugin_id} initialization failed")
                
            except Exception as e:
                logger.error(f"Failed to load plugin {plugin_id}: {e}")
                if plugin_info:
                    plugin_info.error = str(e)
                    self.plugins[plugin_id] = plugin_info
                return False
        
        return False
    
    def _register_plugin_features(self, plugin_id: str, instance: PluginBase):
        """Register plugin commands and hooks"""
        # Register commands
        commands = instance.get_commands()
        for cmd_name, cmd_func in commands.items():
            full_cmd = f"{plugin_id}.{cmd_name}"
            self.commands[full_cmd] = cmd_func
            logger.debug(f"Registered command: {full_cmd}")
        
        # Register hooks
        hooks = instance.get_hooks()
        for hook_name, hook_func in hooks.items():
            if hook_name not in self.hooks:
                self.hooks[hook_name] = []
            self.hooks[hook_name].append(hook_func)
            logger.debug(f"Registered hook: {hook_name} for {plugin_id}")
    
    async def unload_plugin(self, plugin_id: str) -> bool:
        """Unload a plugin"""
        async with self._lock:
            if plugin_id not in self.plugins:
                logger.warning(f"Plugin {plugin_id} not found")
                return False
            
            plugin_info = self.plugins[plugin_id]
            
            if not plugin_info.loaded:
                logger.info(f"Plugin {plugin_id} not loaded")
                return True
            
            try:
                # Cleanup plugin
                if plugin_info.instance:
                    await plugin_info.instance.cleanup()
                
                # Unregister commands
                commands_to_remove = [
                    cmd for cmd in self.commands 
                    if cmd.startswith(f"{plugin_id}.")
                ]
                for cmd in commands_to_remove:
                    del self.commands[cmd]
                
                # Unregister hooks
                if plugin_info.instance:
                    hooks = plugin_info.instance.get_hooks()
                    for hook_name, hook_func in hooks.items():
                        if hook_name in self.hooks:
                            self.hooks[hook_name] = [
                                h for h in self.hooks[hook_name] 
                                if h != hook_func
                            ]
                
                # Remove from sys.modules
                module_name = f"plugin_{plugin_id}"
                if module_name in sys.modules:
                    del sys.modules[module_name]
                
                # Clear plugin info
                plugin_info.module = None
                plugin_info.instance = None
                plugin_info.loaded = False
                
                logger.info(f"Plugin {plugin_id} unloaded successfully")
                return True
                
            except Exception as e:
                logger.error(f"Failed to unload plugin {plugin_id}: {e}")
                return False
    
    async def reload_plugin(self, plugin_id: str) -> bool:
        """Reload a plugin"""
        await self.unload_plugin(plugin_id)
        return await self.load_plugin(plugin_id)
    
    async def execute_command(self, command: str, *args, **kwargs) -> Any:
        """Execute a plugin command"""
        if command not in self.commands:
            raise ValueError(f"Command {command} not found")
        
        cmd_func = self.commands[command]
        
        if asyncio.iscoroutinefunction(cmd_func):
            return await cmd_func(*args, **kwargs)
        else:
            return cmd_func(*args, **kwargs)
    
    async def trigger_hook(self, hook_name: str, *args, **kwargs) -> List[Any]:
        """Trigger a hook across all plugins"""
        if hook_name not in self.hooks:
            return []
        
        results = []
        for hook_func in self.hooks[hook_name]:
            try:
                if asyncio.iscoroutinefunction(hook_func):
                    result = await hook_func(*args, **kwargs)
                else:
                    result = hook_func(*args, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error(f"Hook {hook_name} error: {e}")
        
        return results
    
    def get_plugin_info(self, plugin_id: str) -> Optional[PluginInfo]:
        """Get plugin information"""
        return self.plugins.get(plugin_id)
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all plugins"""
        return [
            {
                'id': plugin_id,
                'name': info.metadata.name,
                'version': info.metadata.version,
                'description': info.metadata.description,
                'loaded': info.loaded,
                'enabled': info.enabled,
                'error': info.error
            }
            for plugin_id, info in self.plugins.items()
        ]
    
    def list_commands(self) -> List[str]:
        """List all available commands"""
        return list(self.commands.keys())
    
    def list_hooks(self) -> Dict[str, int]:
        """List all hooks and their listener count"""
        return {
            hook_name: len(listeners)
            for hook_name, listeners in self.hooks.items()
        }

# Global instance
_plugin_manager: Optional[DynamicPluginManager] = None

def get_plugin_manager() -> DynamicPluginManager:
    """Get or create global plugin manager"""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = DynamicPluginManager()
    return _plugin_manager
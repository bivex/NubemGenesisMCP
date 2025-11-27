"""
Command Registry System for NubemClaude Framework
"""

import inspect
import asyncio
from typing import Callable, Dict, Any, List, Optional, Union
from functools import wraps
import logging

logger = logging.getLogger(__name__)

class CommandRegistry:
    """Registry for all framework commands"""
    
    def __init__(self):
        self.commands: Dict[str, Dict[str, Any]] = {}
        self.categories: Dict[str, List[str]] = {}
        self.aliases: Dict[str, str] = {}
        
    def register(self, name: str, description: str, category: str = "general", aliases: List[str] = None):
        """Decorator to register a command"""
        def decorator(func: Callable):
            # Get function signature
            sig = inspect.signature(func)
            
            # Store command info
            self.commands[name] = {
                'function': func,
                'description': description,
                'category': category,
                'parameters': sig.parameters,
                'is_async': inspect.iscoroutinefunction(func),
                'aliases': aliases or []
            }
            
            # Register category
            if category not in self.categories:
                self.categories[category] = []
            self.categories[category].append(name)
            
            # Register aliases
            if aliases:
                for alias in aliases:
                    self.aliases[alias] = name
            
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                if inspect.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
            
            return async_wrapper
        
        return decorator
    
    def register_dynamic(self, name: str, description: str, handler: Optional[Callable] = None):
        """Register a command dynamically (without decorator)"""
        if handler:
            self.commands[name] = {
                'function': handler,
                'description': description,
                'category': 'dynamic',
                'parameters': inspect.signature(handler).parameters if handler else {},
                'is_async': inspect.iscoroutinefunction(handler) if handler else False,
                'aliases': []
            }
    
    def has_command(self, name: str) -> bool:
        """Check if a command exists"""
        # Check direct name or alias
        return name in self.commands or name in self.aliases
    
    def get_command(self, name: str) -> Optional[Dict[str, Any]]:
        """Get command info"""
        # Resolve alias if needed
        if name in self.aliases:
            name = self.aliases[name]
        
        return self.commands.get(name)
    
    async def execute(self, command: str, **kwargs) -> Any:
        """Execute a command"""
        try:
            # Resolve alias
            if command in self.aliases:
                command = self.aliases[command]
            
            if command not in self.commands:
                raise ValueError(f"Command '{command}' not found")
            
            cmd_info = self.commands[command]
            func = cmd_info['function']
            
            # Validate parameters
            self._validate_parameters(cmd_info, kwargs)
            
            # Execute
            if cmd_info['is_async']:
                result = await func(**kwargs)
            else:
                result = func(**kwargs)
            
            logger.info(f"Executed command: {command}")
            return result
            
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            raise
    
    def _validate_parameters(self, cmd_info: Dict[str, Any], provided: Dict[str, Any]):
        """Validate provided parameters against command signature"""
        params = cmd_info['parameters']
        
        for param_name, param in params.items():
            # Skip self/cls
            if param_name in ['self', 'cls']:
                continue
            
            # Check required parameters
            if param.default == inspect.Parameter.empty and param_name not in provided:
                raise ValueError(f"Missing required parameter: {param_name}")
            
            # Type validation could be added here
    
    def list_commands(self) -> Dict[str, Dict[str, Any]]:
        """List all commands"""
        return {
            name: {
                'description': info['description'],
                'category': info['category'],
                'parameters': {
                    pname: str(param.annotation) if param.annotation != inspect.Parameter.empty else 'Any'
                    for pname, param in info['parameters'].items()
                    if pname not in ['self', 'cls']
                },
                'aliases': info['aliases']
            }
            for name, info in self.commands.items()
        }
    
    def list_by_category(self, category: str) -> List[str]:
        """List commands in a specific category"""
        return self.categories.get(category, [])
    
    def search_commands(self, query: str) -> List[str]:
        """Search commands by name or description"""
        query_lower = query.lower()
        results = []
        
        for name, info in self.commands.items():
            if (query_lower in name.lower() or 
                query_lower in info['description'].lower()):
                results.append(name)
        
        return results
    
    def get_help(self, command: str) -> str:
        """Get detailed help for a command"""
        if command in self.aliases:
            command = self.aliases[command]
        
        if command not in self.commands:
            return f"Command '{command}' not found"
        
        info = self.commands[command]
        
        help_text = f"Command: {command}\n"
        help_text += f"Description: {info['description']}\n"
        help_text += f"Category: {info['category']}\n"
        
        if info['aliases']:
            help_text += f"Aliases: {', '.join(info['aliases'])}\n"
        
        if info['parameters']:
            help_text += "\nParameters:\n"
            for pname, param in info['parameters'].items():
                if pname in ['self', 'cls']:
                    continue
                
                param_type = str(param.annotation) if param.annotation != inspect.Parameter.empty else 'Any'
                required = param.default == inspect.Parameter.empty
                
                help_text += f"  - {pname}: {param_type}"
                if not required:
                    help_text += f" (default: {param.default})"
                else:
                    help_text += " (required)"
                help_text += "\n"
        
        return help_text


class CommandBuilder:
    """Builder for creating complex commands"""
    
    def __init__(self, registry: CommandRegistry):
        self.registry = registry
        self.command_chain = []
    
    def add(self, command: str, **kwargs):
        """Add a command to the chain"""
        self.command_chain.append((command, kwargs))
        return self
    
    async def execute(self) -> List[Any]:
        """Execute all commands in the chain"""
        results = []
        
        for command, kwargs in self.command_chain:
            result = await self.registry.execute(command, **kwargs)
            results.append(result)
            
            # Pass result to next command if needed
            if len(results) > 0 and '_previous_result' not in kwargs:
                kwargs['_previous_result'] = result
        
        return results
    
    def clear(self):
        """Clear the command chain"""
        self.command_chain = []
        return self


class CommandMacro:
    """Macro system for command combinations"""
    
    def __init__(self, registry: CommandRegistry):
        self.registry = registry
        self.macros: Dict[str, List[tuple]] = {}
    
    def define(self, name: str, commands: List[tuple]):
        """Define a macro"""
        self.macros[name] = commands
    
    async def execute(self, name: str, **global_kwargs) -> List[Any]:
        """Execute a macro"""
        if name not in self.macros:
            raise ValueError(f"Macro '{name}' not found")
        
        results = []
        for command, kwargs in self.macros[name]:
            # Merge global kwargs with command-specific kwargs
            merged_kwargs = {**global_kwargs, **kwargs}
            result = await self.registry.execute(command, **merged_kwargs)
            results.append(result)
        
        return results
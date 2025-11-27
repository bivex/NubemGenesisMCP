"""
Lazy Loading System for NubemSuperFClaude
Optimizes memory usage and startup time by loading modules only when needed
"""

import importlib
import sys
from functools import lru_cache
from typing import Any, Dict, Optional, Set
import logging
from contextlib import contextmanager
import time

logger = logging.getLogger(__name__)


class LazyLoader:
    """
    Lazy load heavy modules only when needed to optimize performance.
    Implements singleton pattern with thread-safe loading.
    """
    
    _instance: Optional['LazyLoader'] = None
    _lock = None
    
    def __new__(cls) -> 'LazyLoader':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._modules: Dict[str, Any] = {}
        self._loading_times: Dict[str, float] = {}
        self._access_count: Dict[str, int] = {}
        self._preload_list: Set[str] = set()
        self._initialized = True
        
        # Thread lock for thread-safe loading
        import threading
        self.__class__._lock = threading.Lock()
    
    @lru_cache(maxsize=128)
    def load(self, module_name: str, attribute: Optional[str] = None) -> Any:
        """
        Load a module or specific attribute from a module lazily.
        
        Args:
            module_name: Full module path (e.g., 'numpy', 'pandas.DataFrame')
            attribute: Optional specific attribute to import from module
            
        Returns:
            The loaded module or attribute
        """
        with self._lock:
            cache_key = f"{module_name}:{attribute}" if attribute else module_name
            
            if cache_key not in self._modules:
                start_time = time.time()
                
                try:
                    if attribute:
                        # Import specific attribute from module
                        module = importlib.import_module(module_name)
                        self._modules[cache_key] = getattr(module, attribute)
                    else:
                        # Import entire module
                        self._modules[cache_key] = importlib.import_module(module_name)
                    
                    load_time = time.time() - start_time
                    self._loading_times[cache_key] = load_time
                    self._access_count[cache_key] = 0
                    
                    logger.debug(f"Loaded {cache_key} in {load_time:.3f}s")
                    
                except ImportError as e:
                    logger.error(f"Failed to import {cache_key}: {e}")
                    raise
            
            self._access_count[cache_key] = self._access_count.get(cache_key, 0) + 1
            return self._modules[cache_key]
    
    def preload(self, *module_names: str) -> None:
        """
        Preload specific modules during initialization.
        Useful for critical modules that are always needed.
        
        Args:
            *module_names: Module names to preload
        """
        for module_name in module_names:
            self._preload_list.add(module_name)
            try:
                self.load(module_name)
                logger.info(f"Preloaded module: {module_name}")
            except ImportError as e:
                logger.warning(f"Failed to preload {module_name}: {e}")
    
    @contextmanager
    def batch_load(self):
        """
        Context manager for batch loading multiple modules efficiently.
        """
        batch_start = time.time()
        modules_before = len(self._modules)
        
        yield self
        
        modules_loaded = len(self._modules) - modules_before
        total_time = time.time() - batch_start
        
        if modules_loaded > 0:
            logger.info(f"Batch loaded {modules_loaded} modules in {total_time:.3f}s")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about loaded modules.
        
        Returns:
            Dictionary with loading statistics
        """
        return {
            'total_modules': len(self._modules),
            'total_load_time': sum(self._loading_times.values()),
            'most_accessed': sorted(
                self._access_count.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10],
            'slowest_loads': sorted(
                self._loading_times.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10],
            'preloaded': list(self._preload_list)
        }
    
    def clear_cache(self, module_name: Optional[str] = None) -> None:
        """
        Clear cached modules to free memory.
        
        Args:
            module_name: Specific module to clear, or None to clear all
        """
        if module_name:
            keys_to_remove = [k for k in self._modules if k.startswith(module_name)]
            for key in keys_to_remove:
                del self._modules[key]
                if key in self._loading_times:
                    del self._loading_times[key]
                if key in self._access_count:
                    del self._access_count[key]
            logger.info(f"Cleared cache for {module_name}")
        else:
            self._modules.clear()
            self._loading_times.clear()
            self._access_count.clear()
            self.load.cache_clear()
            logger.info("Cleared all module cache")


class LazyImportProxy:
    """
    Proxy class for lazy importing of modules with attribute access.
    """
    
    def __init__(self, module_name: str):
        self._module_name = module_name
        self._module = None
        self._loader = LazyLoader()
    
    def __getattr__(self, name: str) -> Any:
        """
        Lazy load the module on first attribute access.
        """
        if self._module is None:
            self._module = self._loader.load(self._module_name)
        return getattr(self._module, name)
    
    def __call__(self, *args, **kwargs):
        """
        Support calling the module if it's callable.
        """
        if self._module is None:
            self._module = self._loader.load(self._module_name)
        return self._module(*args, **kwargs)


def lazy_import(module_name: str) -> LazyImportProxy:
    """
    Create a lazy import proxy for a module.
    
    Args:
        module_name: Name of the module to import lazily
        
    Returns:
        LazyImportProxy that loads the module on first use
        
    Example:
        numpy = lazy_import('numpy')
        # numpy is not loaded yet
        array = numpy.array([1, 2, 3])  # numpy loads here on first use
    """
    return LazyImportProxy(module_name)


# Global lazy loader instance
loader = LazyLoader()

# Convenience functions
def preload_essentials():
    """Preload essential modules that are always needed."""
    loader.preload(
        'os',
        'sys',
        'asyncio',
        'logging',
        'json',
        'typing'
    )


def get_lazy_stats() -> Dict[str, Any]:
    """Get global lazy loading statistics."""
    return loader.get_stats()


# Example usage in other modules:
"""
from core.lazy_loader import lazy_import, loader

# Option 1: Using lazy_import for proxy
numpy = lazy_import('numpy')
pandas = lazy_import('pandas')

# Option 2: Using loader directly
def process_data():
    np = loader.load('numpy')
    pd = loader.load('pandas')
    
# Option 3: Loading specific attributes
def create_dataframe():
    DataFrame = loader.load('pandas', 'DataFrame')
    return DataFrame(data)
"""
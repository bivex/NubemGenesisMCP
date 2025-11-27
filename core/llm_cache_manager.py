#!/usr/bin/env python3
"""
LLM Response Cache Manager for NubemSuperFClaude
Caches responses to avoid redundant API calls
"""

import os
import json
import hashlib
import time
from pathlib import Path
from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta
from core.safe_serialization import safe_dumps, safe_loads, safe_dumps_bytes, safe_loads_bytes

class LLMCacheManager:
    """Manages caching of LLM responses"""
    
    def __init__(self, cache_dir: str = None, ttl_seconds: int = 300):
        """
        Initialize cache manager
        
        Args:
            cache_dir: Directory for cache storage
            ttl_seconds: Time to live for cache entries in seconds
        """
        self.cache_dir = Path(cache_dir or os.path.expanduser("~/.nubem_cache/llm_responses"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = int(os.environ.get('NUBEM_CACHE_TTL', ttl_seconds))
        self.stats_file = self.cache_dir / "cache_stats.json"
        self.load_stats()
    
    def load_stats(self):
        """Load cache statistics"""
        if self.stats_file.exists():
            with open(self.stats_file, 'r') as f:
                self.stats = json.load(f)
        else:
            self.stats = {
                'hits': 0,
                'misses': 0,
                'saves': 0,
                'total_saved_time': 0,
                'total_saved_tokens': 0,
                'total_saved_cost': 0
            }
    
    def save_stats(self):
        """Save cache statistics"""
        with open(self.stats_file, 'w') as f:
            json.dump(self.stats, f, indent=2)
    
    def get_cache_key(self, prompt: str, model: str) -> str:
        """Generate cache key from prompt and model"""
        content = f"{model}:{prompt}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    def get_cache_path(self, cache_key: str) -> Path:
        """Get file path for cache entry"""
        # Use subdirectories to avoid too many files in one directory
        subdir = cache_key[:2]
        return self.cache_dir / subdir / f"{cache_key}.cache"
    
    def is_valid(self, cache_path: Path) -> bool:
        """Check if cache entry is still valid"""
        if not cache_path.exists():
            return False
        
        # Check age
        age = time.time() - cache_path.stat().st_mtime
        return age < self.ttl_seconds
    
    def get(self, prompt: str, model: str) -> Optional[Dict[str, Any]]:
        """
        Get cached response if available and valid
        
        Returns:
            Cached response dict or None if not found/expired
        """
        cache_key = self.get_cache_key(prompt, model)
        cache_path = self.get_cache_path(cache_key)
        
        if self.is_valid(cache_path):
            try:
                with open(cache_path, 'rb') as f:
                    data = safe_loads_bytes(f.read())
                
                self.stats['hits'] += 1
                self.stats['total_saved_time'] += data.get('response_time', 0)
                self.save_stats()
                
                if os.environ.get('NUBEM_DEBUG') == 'true':
                    print(f"🎯 Cache HIT for {model}: {prompt[:50]}...")
                
                return data
            except Exception as e:
                if os.environ.get('NUBEM_DEBUG') == 'true':
                    print(f"❌ Cache read error: {e}")
                return None
        
        self.stats['misses'] += 1
        self.save_stats()
        
        if os.environ.get('NUBEM_DEBUG') == 'true':
            print(f"💨 Cache MISS for {model}: {prompt[:50]}...")
        
        return None
    
    def set(self, prompt: str, model: str, response: str, 
            metadata: Optional[Dict] = None) -> bool:
        """
        Cache a response
        
        Args:
            prompt: Original prompt
            model: Model ID
            response: Response text
            metadata: Additional metadata (tokens, cost, etc.)
        
        Returns:
            True if cached successfully
        """
        cache_key = self.get_cache_key(prompt, model)
        cache_path = self.get_cache_path(cache_key)
        
        # Create subdirectory if needed
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            'prompt': prompt,
            'model': model,
            'response': response,
            'timestamp': datetime.now().isoformat(),
            'ttl': self.ttl_seconds,
            **(metadata or {})
        }
        
        try:
            with open(cache_path, 'wb') as f:
                f.write(safe_dumps_bytes(data))
            
            self.stats['saves'] += 1
            if metadata:
                self.stats['total_saved_tokens'] += metadata.get('tokens', 0)
                self.stats['total_saved_cost'] += metadata.get('cost', 0)
            self.save_stats()
            
            if os.environ.get('NUBEM_DEBUG') == 'true':
                print(f"💾 Cached response for {model}")
            
            return True
        except Exception as e:
            if os.environ.get('NUBEM_DEBUG') == 'true':
                print(f"❌ Cache write error: {e}")
            return False
    
    def clear_expired(self) -> int:
        """
        Clear expired cache entries
        
        Returns:
            Number of entries cleared
        """
        cleared = 0
        for cache_file in self.cache_dir.rglob("*.cache"):
            if not self.is_valid(cache_file):
                try:
                    cache_file.unlink()
                    cleared += 1
                except:
                    pass
        
        if os.environ.get('NUBEM_DEBUG') == 'true' and cleared > 0:
            print(f"🗑️ Cleared {cleared} expired cache entries")
        
        return cleared
    
    def clear_all(self) -> int:
        """
        Clear all cache entries
        
        Returns:
            Number of entries cleared
        """
        cleared = 0
        for cache_file in self.cache_dir.rglob("*.cache"):
            try:
                cache_file.unlink()
                cleared += 1
            except:
                pass
        
        # Reset stats
        self.stats = {
            'hits': 0,
            'misses': 0,
            'saves': 0,
            'total_saved_time': 0,
            'total_saved_tokens': 0,
            'total_saved_cost': 0
        }
        self.save_stats()
        
        return cleared
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get cache information and statistics"""
        total_size = sum(f.stat().st_size for f in self.cache_dir.rglob("*.cache"))
        total_entries = len(list(self.cache_dir.rglob("*.cache")))
        
        # Calculate hit rate
        total_requests = self.stats['hits'] + self.stats['misses']
        hit_rate = (self.stats['hits'] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'cache_dir': str(self.cache_dir),
            'ttl_seconds': self.ttl_seconds,
            'total_entries': total_entries,
            'total_size_mb': round(total_size / 1024 / 1024, 2),
            'hit_rate': round(hit_rate, 2),
            'stats': self.stats
        }
    
    def get_cached_prompts(self, model: Optional[str] = None) -> List[Dict]:
        """Get list of cached prompts"""
        cached = []
        for cache_file in self.cache_dir.rglob("*.cache"):
            if self.is_valid(cache_file):
                try:
                    with open(cache_file, 'rb') as f:
                        data = safe_loads_bytes(f.read())
                    
                    if model is None or data.get('model') == model:
                        cached.append({
                            'prompt': data['prompt'][:100] + '...' if len(data['prompt']) > 100 else data['prompt'],
                            'model': data['model'],
                            'timestamp': data['timestamp'],
                            'ttl_remaining': self.ttl_seconds - (time.time() - cache_file.stat().st_mtime)
                        })
                except:
                    pass
        
        return sorted(cached, key=lambda x: x['timestamp'], reverse=True)


# CLI interface for cache management
if __name__ == "__main__":
    import sys
    from colorama import init, Fore, Style
    
    init(autoreset=True)
    
    cache = LLMCacheManager()
    
    if len(sys.argv) < 2:
        print(f"{Fore.CYAN}LLM Cache Manager{Style.RESET_ALL}")
        print(f"Usage: {sys.argv[0]} <command>")
        print("\nCommands:")
        print("  info     - Show cache statistics")
        print("  list     - List cached prompts")
        print("  clear    - Clear expired entries")
        print("  reset    - Clear all cache")
        sys.exit(0)
    
    command = sys.argv[1]
    
    if command == "info":
        info = cache.get_cache_info()
        print(f"\n{Fore.CYAN}═══════════════════════════════════════════════════════════{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}📊 LLM Cache Statistics{Style.RESET_ALL}")
        print(f"{Fore.CYAN}═══════════════════════════════════════════════════════════{Style.RESET_ALL}")
        print(f"Cache Directory: {info['cache_dir']}")
        print(f"TTL: {info['ttl_seconds']} seconds")
        print(f"Total Entries: {info['total_entries']}")
        print(f"Total Size: {info['total_size_mb']} MB")
        print(f"Hit Rate: {info['hit_rate']}%")
        print(f"\n{Fore.GREEN}Statistics:{Style.RESET_ALL}")
        for key, value in info['stats'].items():
            print(f"  {key}: {value}")
    
    elif command == "list":
        cached = cache.get_cached_prompts()
        if cached:
            print(f"\n{Fore.CYAN}Cached Prompts ({len(cached)} entries):{Style.RESET_ALL}")
            for entry in cached[:10]:  # Show first 10
                print(f"\n{Fore.YELLOW}Model:{Style.RESET_ALL} {entry['model']}")
                print(f"{Fore.GREEN}Prompt:{Style.RESET_ALL} {entry['prompt']}")
                print(f"{Fore.BLUE}Cached:{Style.RESET_ALL} {entry['timestamp']}")
                print(f"{Fore.MAGENTA}TTL:{Style.RESET_ALL} {int(entry['ttl_remaining'])}s remaining")
        else:
            print(f"{Fore.YELLOW}No cached entries found{Style.RESET_ALL}")
    
    elif command == "clear":
        cleared = cache.clear_expired()
        print(f"{Fore.GREEN}✅ Cleared {cleared} expired entries{Style.RESET_ALL}")
    
    elif command == "reset":
        cleared = cache.clear_all()
        print(f"{Fore.GREEN}✅ Reset cache - removed {cleared} entries{Style.RESET_ALL}")
    
    else:
        print(f"{Fore.RED}Unknown command: {command}{Style.RESET_ALL}")
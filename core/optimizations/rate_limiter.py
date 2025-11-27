"""
Smart Rate Limiting System
"""

import time
from collections import deque, defaultdict
from typing import Dict, Optional
import threading

class SmartRateLimiter:
    """Intelligent rate limiter for API calls"""
    
    def __init__(self):
        self.limits = {
            "openai": {"tpm": 10000, "rpm": 200},    # Tokens/Requests per minute
            "anthropic": {"tpm": 100000, "rpm": 50},
            "google": {"tpm": 1000000, "rpm": 60}
        }
        
        self.usage = defaultdict(lambda: {"tokens": deque(), "requests": deque()})
        self.lock = threading.Lock()
    
    def can_make_request(self, api: str, estimated_tokens: int) -> bool:
        """Check if request can be made within rate limits"""
        with self.lock:
            now = time.time()
            minute_ago = now - 60
            
            # Clean old entries
            usage = self.usage[api]
            usage["tokens"] = deque([t for t in usage["tokens"] if t[0] > minute_ago])
            usage["requests"] = deque([r for r in usage["requests"] if r > minute_ago])
            
            # Check limits
            current_tokens = sum(t[1] for t in usage["tokens"])
            current_requests = len(usage["requests"])
            
            limits = self.limits.get(api, {"tpm": 10000, "rpm": 100})
            
            if current_tokens + estimated_tokens > limits["tpm"]:
                return False
            if current_requests >= limits["rpm"]:
                return False
            
            return True
    
    def record_usage(self, api: str, tokens_used: int):
        """Record API usage for rate limiting"""
        with self.lock:
            now = time.time()
            self.usage[api]["tokens"].append((now, tokens_used))
            self.usage[api]["requests"].append(now)
    
    def get_wait_time(self, api: str) -> float:
        """Get time to wait before next request is allowed"""
        with self.lock:
            now = time.time()
            minute_ago = now - 60
            
            usage = self.usage[api]
            if usage["requests"]:
                oldest_request = min(usage["requests"])
                if oldest_request > minute_ago:
                    return 0
                return 60 - (now - oldest_request)
            return 0
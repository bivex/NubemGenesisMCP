"""
Weighted Load Balancer for API distribution
"""

import random
import time
from typing import Dict, List, Any
from collections import defaultdict
import threading

class WeightedLoadBalancer:
    """Intelligent load balancer with dynamic weight adjustment"""
    
    def __init__(self):
        self.weights = {
            "openai": 30,   # 30% of traffic
            "gemini": 50,   # 50% of traffic (fastest)
            "claude": 20    # 20% of traffic
        }
        self.performance_metrics = defaultdict(lambda: {"latency": [], "errors": 0, "successes": 0})
        self.lock = threading.Lock()
        
    def select_api(self) -> str:
        """Select API based on weighted distribution"""
        total = sum(self.weights.values())
        r = random.uniform(0, total)
        upto = 0
        
        for api, weight in self.weights.items():
            if upto + weight >= r:
                return api
            upto += weight
        return list(self.weights.keys())[0]
    
    def adjust_weights_based_on_performance(self):
        """Dynamically adjust weights based on performance metrics"""
        with self.lock:
            for api in self.weights:
                metrics = self.performance_metrics[api]
                if metrics["latency"] and metrics["successes"] > 0:
                    avg_latency = sum(metrics["latency"]) / len(metrics["latency"])
                    error_rate = metrics["errors"] / (metrics["errors"] + metrics["successes"])
                    
                    # Adjust weight based on performance
                    if avg_latency < 0.5 and error_rate < 0.05:
                        self.weights[api] = min(60, self.weights[api] + 5)
                    elif avg_latency > 1.5 or error_rate > 0.1:
                        self.weights[api] = max(10, self.weights[api] - 5)
    
    def record_performance(self, api: str, latency: float, success: bool):
        """Record API performance metrics"""
        with self.lock:
            metrics = self.performance_metrics[api]
            metrics["latency"].append(latency)
            if success:
                metrics["successes"] += 1
            else:
                metrics["errors"] += 1
            
            # Keep only last 100 latency measurements
            if len(metrics["latency"]) > 100:
                metrics["latency"] = metrics["latency"][-100:]
"""
API Cost Monitor - Real-time tracking and optimization of API costs
"""

import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum
import sqlite3
import threading
import logging

logger = logging.getLogger(__name__)

class APIProvider(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"

@dataclass
class CostProfile:
    """Cost profile for each model"""
    provider: str
    model: str
    input_cost_per_1k: float  # USD per 1000 tokens
    output_cost_per_1k: float  # USD per 1000 tokens
    
class APIUsageMonitor:
    """Monitor and track API usage and costs in real-time"""
    
    # Updated pricing as of 2025
    COSTS = {
        # OpenAI
        "gpt-3.5-turbo": {"input": 0.0015, "output": 0.002},
        "gpt-3.5-turbo-16k": {"input": 0.003, "output": 0.004},
        "gpt-4": {"input": 0.03, "output": 0.06},
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
        "gpt-4o": {"input": 0.005, "output": 0.015},
        
        # Anthropic Claude
        "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
        "claude-3-sonnet": {"input": 0.003, "output": 0.015},
        "claude-3-opus": {"input": 0.015, "output": 0.075},
        "claude-2.1": {"input": 0.008, "output": 0.024},
        
        # Google Gemini
        "gemini-1.5-flash": {"input": 0.00001, "output": 0.00002},
        "gemini-1.5-pro": {"input": 0.00035, "output": 0.0014},
        "gemini-2.0-flash": {"input": 0.00001, "output": 0.00002},
        "gemini-pro": {"input": 0.00025, "output": 0.0005},
    }
    
    def __init__(self, db_path: str = "api_usage.db", daily_limit: float = 50.0):
        self.db_path = db_path
        self.daily_limit = daily_limit
        self.current_costs = {}
        self.lock = threading.Lock()
        self._init_database()
        self.cost_alerts = []
        
    def _init_database(self):
        """Initialize SQLite database for persistent storage"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                provider TEXT,
                model TEXT,
                input_tokens INTEGER,
                output_tokens INTEGER,
                cost REAL,
                request_type TEXT,
                user_id TEXT,
                session_id TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cost_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                alert_type TEXT,
                message TEXT,
                cost_at_time REAL
            )
        """)
        
        conn.commit()
        conn.close()
    
    def track_usage(self, 
                   api: str, 
                   model: str,
                   input_tokens: int, 
                   output_tokens: int,
                   request_type: str = "general",
                   user_id: str = "default",
                   session_id: str = None) -> Dict[str, Any]:
        """Track API usage and calculate cost"""
        
        with self.lock:
            # Calculate cost
            cost = self.calculate_cost(model, input_tokens, output_tokens)
            
            # Store in database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO api_usage 
                (provider, model, input_tokens, output_tokens, cost, request_type, user_id, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (api, model, input_tokens, output_tokens, cost, request_type, user_id, session_id))
            
            conn.commit()
            conn.close()
            
            # Update current costs
            today = datetime.now().strftime("%Y-%m-%d")
            if today not in self.current_costs:
                self.current_costs[today] = 0
            self.current_costs[today] += cost
            
            # Check for alerts
            daily_total = self.get_daily_cost()
            
            if daily_total > self.daily_limit:
                self._trigger_alert("LIMIT_EXCEEDED", 
                                   f"Daily limit of ${self.daily_limit} exceeded! Current: ${daily_total:.2f}")
                
                # Auto-switch to cheaper model
                cheaper_model = self._suggest_cheaper_alternative(model)
                
                return {
                    "cost": cost,
                    "daily_total": daily_total,
                    "limit_exceeded": True,
                    "suggested_model": cheaper_model,
                    "alert": f"Switching to {cheaper_model} to reduce costs"
                }
            
            return {
                "cost": cost,
                "daily_total": daily_total,
                "limit_exceeded": False,
                "remaining_budget": self.daily_limit - daily_total
            }
    
    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for a specific API call"""
        if model not in self.COSTS:
            logger.warning(f"Unknown model {model}, using default pricing")
            return (input_tokens * 0.001 + output_tokens * 0.002) / 1000
        
        costs = self.COSTS[model]
        input_cost = (input_tokens / 1000) * costs["input"]
        output_cost = (output_tokens / 1000) * costs["output"]
        
        return round(input_cost + output_cost, 6)
    
    def get_daily_cost(self, date: str = None) -> float:
        """Get total cost for a specific day"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT SUM(cost) FROM api_usage 
            WHERE DATE(timestamp) = ?
        """, (date,))
        
        result = cursor.fetchone()[0]
        conn.close()
        
        return result if result else 0.0
    
    def get_usage_report(self, days: int = 7) -> Dict[str, Any]:
        """Generate comprehensive usage report"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Total costs by model
        cursor.execute("""
            SELECT model, 
                   COUNT(*) as requests,
                   SUM(input_tokens) as total_input,
                   SUM(output_tokens) as total_output,
                   SUM(cost) as total_cost
            FROM api_usage 
            WHERE timestamp >= ?
            GROUP BY model
            ORDER BY total_cost DESC
        """, (start_date,))
        
        model_stats = []
        for row in cursor.fetchall():
            model_stats.append({
                "model": row[0],
                "requests": row[1],
                "input_tokens": row[2],
                "output_tokens": row[3],
                "total_cost": round(row[4], 2)
            })
        
        # Daily costs
        cursor.execute("""
            SELECT DATE(timestamp) as date, SUM(cost) as daily_cost
            FROM api_usage 
            WHERE timestamp >= ?
            GROUP BY DATE(timestamp)
            ORDER BY date
        """, (start_date,))
        
        daily_costs = {row[0]: round(row[1], 2) for row in cursor.fetchall()}
        
        # Top request types
        cursor.execute("""
            SELECT request_type, COUNT(*) as count, SUM(cost) as total_cost
            FROM api_usage 
            WHERE timestamp >= ?
            GROUP BY request_type
            ORDER BY total_cost DESC
            LIMIT 10
        """, (start_date,))
        
        request_types = []
        for row in cursor.fetchall():
            request_types.append({
                "type": row[0],
                "count": row[1],
                "cost": round(row[2], 2)
            })
        
        conn.close()
        
        return {
            "period": f"{days} days",
            "total_cost": sum(m["total_cost"] for m in model_stats),
            "model_breakdown": model_stats,
            "daily_costs": daily_costs,
            "request_types": request_types,
            "average_daily_cost": round(sum(daily_costs.values()) / len(daily_costs) if daily_costs else 0, 2)
        }
    
    def _suggest_cheaper_alternative(self, current_model: str) -> str:
        """Suggest a cheaper alternative model"""
        alternatives = {
            "gpt-4": "gpt-3.5-turbo",
            "gpt-4-turbo": "gpt-3.5-turbo",
            "claude-3-opus": "claude-3-haiku-20240307",
            "claude-3-sonnet": "claude-3-haiku-20240307",
            "gemini-1.5-pro": "gemini-1.5-flash",
        }
        
        return alternatives.get(current_model, "gemini-1.5-flash")  # Gemini Flash as ultimate fallback
    
    def _trigger_alert(self, alert_type: str, message: str):
        """Trigger a cost alert"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO cost_alerts (alert_type, message, cost_at_time)
            VALUES (?, ?, ?)
        """, (alert_type, message, self.get_daily_cost()))
        
        conn.commit()
        conn.close()
        
        self.cost_alerts.append({
            "timestamp": datetime.now().isoformat(),
            "type": alert_type,
            "message": message
        })
        
        logger.warning(f"COST ALERT: {message}")
    
    def set_budget_alerts(self, thresholds: List[float]):
        """Set budget alert thresholds (e.g., [25, 50, 75] for 25%, 50%, 75% of daily limit)"""
        self.alert_thresholds = [self.daily_limit * (t/100) for t in thresholds]
    
    def optimize_costs(self) -> Dict[str, Any]:
        """Provide cost optimization recommendations"""
        report = self.get_usage_report(7)
        
        recommendations = []
        
        # Check for expensive models
        for model_stat in report["model_breakdown"]:
            model = model_stat["model"]
            if "gpt-4" in model and model_stat["total_cost"] > 10:
                recommendations.append({
                    "priority": "HIGH",
                    "action": f"Replace {model} with gpt-3.5-turbo for non-critical tasks",
                    "potential_savings": f"${model_stat['total_cost'] * 0.9:.2f}"
                })
            elif "opus" in model:
                recommendations.append({
                    "priority": "HIGH", 
                    "action": f"Use claude-3-haiku instead of {model} for simple tasks",
                    "potential_savings": f"${model_stat['total_cost'] * 0.95:.2f}"
                })
        
        # Check for high-volume patterns
        if report["total_cost"] > self.daily_limit * 7:
            recommendations.append({
                "priority": "CRITICAL",
                "action": "Implement caching to reduce redundant API calls",
                "potential_savings": f"${report['total_cost'] * 0.3:.2f}"
            })
        
        return {
            "current_weekly_cost": report["total_cost"],
            "projected_monthly_cost": report["average_daily_cost"] * 30,
            "recommendations": recommendations,
            "cheapest_models": ["gemini-1.5-flash", "claude-3-haiku-20240307", "gpt-3.5-turbo"]
        }


class CostTracker:
    """Simple interface for tracking costs across the application"""
    
    def __init__(self, monitor: APIUsageMonitor):
        self.monitor = monitor
        
    def track(self, api: str, model: str, prompt: str, response: str, **kwargs) -> Dict[str, Any]:
        """Track API call with automatic token counting"""
        # Rough token estimation (4 chars ≈ 1 token)
        input_tokens = len(prompt) // 4
        output_tokens = len(response) // 4
        
        return self.monitor.track_usage(
            api=api,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            **kwargs
        )
    
    def get_current_spend(self) -> float:
        """Get current daily spend"""
        return self.monitor.get_daily_cost()
    
    def is_within_budget(self) -> bool:
        """Check if within daily budget"""
        return self.get_current_spend() < self.monitor.daily_limit


if __name__ == "__main__":
    # Test the cost monitor
    monitor = APIUsageMonitor(daily_limit=10.0)
    
    # Simulate some API calls
    print("Testing Cost Monitor\n" + "="*50)
    
    # Track a GPT-4 call
    result = monitor.track_usage("openai", "gpt-4", 1000, 500)
    print(f"GPT-4 call: ${result['cost']:.4f}, Daily total: ${result['daily_total']:.2f}")
    
    # Track a Gemini call
    result = monitor.track_usage("google", "gemini-1.5-flash", 2000, 1000)
    print(f"Gemini call: ${result['cost']:.4f}, Daily total: ${result['daily_total']:.2f}")
    
    # Get usage report
    report = monitor.get_usage_report(7)
    print(f"\nWeekly Report: ${report['total_cost']:.2f}")
    
    # Get optimization recommendations
    optimizations = monitor.optimize_costs()
    print(f"\nOptimization Recommendations:")
    for rec in optimizations["recommendations"]:
        print(f"  [{rec['priority']}] {rec['action']}")
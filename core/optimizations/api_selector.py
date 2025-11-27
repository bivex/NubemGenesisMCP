"""
Smart API Selector - Optimized selection based on speed, cost, and capabilities
"""

import time
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class Priority(Enum):
    SPEED = "speed"
    COST = "cost"
    QUALITY = "quality"
    BALANCED = "balanced"

class TaskType(Enum):
    SIMPLE_QUERY = "simple_query"
    TRANSLATION = "translation"
    CODE_GENERATION = "code_generation"
    COMPLEX_REASONING = "complex_reasoning"
    CONVERSATION = "conversation"
    SUMMARIZATION = "summarization"
    CREATIVE_WRITING = "creative_writing"
    DATA_ANALYSIS = "data_analysis"
    VISION = "vision"
    LONG_CONTEXT = "long_context"
    REAL_TIME = "real_time"

@dataclass
class APIProfile:
    """Profile for each API with performance metrics"""
    name: str
    models: List[str]
    avg_latency: float  # seconds
    cost_per_1k_tokens: float  # USD
    max_context: int
    capabilities: List[str]
    reliability_score: float  # 0-1

class SmartAPISelector:
    """Intelligent API selector based on task requirements and priorities"""
    
    def __init__(self):
        self.api_profiles = self._initialize_profiles()
        self.performance_history = {}
        self.task_mapping = self._initialize_task_mapping()
        
    def _initialize_profiles(self) -> Dict[str, APIProfile]:
        """Initialize API profiles with real test data"""
        return {
            "gemini": APIProfile(
                name="gemini",
                models=["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"],
                avg_latency=0.45,  # From tests
                cost_per_1k_tokens=0.00003,  # Cheapest
                max_context=1000000,
                capabilities=["vision", "long_context", "fast_response", "safety_filters"],
                reliability_score=0.98  # Very consistent in tests
            ),
            "claude": APIProfile(
                name="claude",
                models=["claude-3-haiku-20240307", "claude-3-sonnet", "claude-3-opus"],
                avg_latency=0.70,  # From tests
                cost_per_1k_tokens=0.00375,  # Haiku pricing
                max_context=200000,
                capabilities=["reasoning", "code", "analysis", "conversation"],
                reliability_score=0.95
            ),
            "openai": APIProfile(
                name="openai",
                models=["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"],
                avg_latency=0.89,  # From tests
                cost_per_1k_tokens=0.002,  # GPT-3.5 pricing
                max_context=128000,
                capabilities=["code_generation", "reasoning", "creativity", "json_mode"],
                reliability_score=0.90  # More variable in tests
            )
        }
    
    def _initialize_task_mapping(self) -> Dict[TaskType, Dict[Priority, str]]:
        """Map tasks to optimal APIs based on priority"""
        return {
            TaskType.SIMPLE_QUERY: {
                Priority.SPEED: "gemini",
                Priority.COST: "gemini",
                Priority.QUALITY: "claude",
                Priority.BALANCED: "gemini"
            },
            TaskType.CODE_GENERATION: {
                Priority.SPEED: "gemini",
                Priority.COST: "gemini",
                Priority.QUALITY: "openai",  # GPT-4
                Priority.BALANCED: "claude"
            },
            TaskType.COMPLEX_REASONING: {
                Priority.SPEED: "claude",
                Priority.COST: "gemini",
                Priority.QUALITY: "openai",  # GPT-4
                Priority.BALANCED: "claude"
            },
            TaskType.CREATIVE_WRITING: {
                Priority.SPEED: "gemini",
                Priority.COST: "gemini",
                Priority.QUALITY: "openai",
                Priority.BALANCED: "claude"
            },
            TaskType.TRANSLATION: {
                Priority.SPEED: "gemini",
                Priority.COST: "gemini",
                Priority.QUALITY: "claude",
                Priority.BALANCED: "gemini"
            },
            TaskType.VISION: {
                Priority.SPEED: "gemini",
                Priority.COST: "gemini",
                Priority.QUALITY: "gemini",  # Best for vision
                Priority.BALANCED: "gemini"
            },
            TaskType.LONG_CONTEXT: {
                Priority.SPEED: "gemini",  # 1M context
                Priority.COST: "gemini",
                Priority.QUALITY: "claude",  # 200K context
                Priority.BALANCED: "gemini"
            },
            TaskType.REAL_TIME: {
                Priority.SPEED: "gemini",  # Fastest
                Priority.COST: "gemini",
                Priority.QUALITY: "gemini",
                Priority.BALANCED: "gemini"
            }
        }
    
    def select_api_for_task(self, 
                           task_type: TaskType, 
                           priority: Priority = Priority.BALANCED,
                           context_length: int = 0,
                           required_capabilities: List[str] = None) -> Dict[str, Any]:
        """
        Select optimal API for a given task
        
        Returns:
            Dict with api name, model, and reasoning
        """
        # Check context length requirements
        if context_length > 128000:
            if context_length > 200000:
                return {
                    "api": "gemini",
                    "model": "gemini-1.5-pro",
                    "reason": f"Only Gemini supports {context_length} tokens context"
                }
            return {
                "api": "claude",
                "model": "claude-3-opus",
                "reason": f"Claude best for {context_length} tokens with quality"
            }
        
        # Check capability requirements
        if required_capabilities:
            best_match = self._match_capabilities(required_capabilities)
            if best_match:
                return best_match
        
        # Use task mapping
        if task_type in self.task_mapping:
            api_name = self.task_mapping[task_type].get(priority, "gemini")
            return self._get_optimal_model(api_name, task_type, priority)
        
        # Default fallback
        return self._get_optimal_model("gemini", task_type, priority)
    
    def _match_capabilities(self, required: List[str]) -> Optional[Dict[str, Any]]:
        """Match required capabilities to best API"""
        best_match = None
        best_score = 0
        
        for api_name, profile in self.api_profiles.items():
            matches = sum(1 for cap in required if cap in profile.capabilities)
            if matches > best_score:
                best_score = matches
                best_match = api_name
        
        if best_match:
            return {
                "api": best_match,
                "model": self.api_profiles[best_match].models[0],
                "reason": f"Best match for capabilities: {required}"
            }
        return None
    
    def _get_optimal_model(self, api_name: str, task_type: TaskType, priority: Priority) -> Dict[str, Any]:
        """Get optimal model configuration for API"""
        profile = self.api_profiles[api_name]
        
        # Model selection logic
        model_index = 0  # Default to cheapest/fastest
        if priority == Priority.QUALITY:
            model_index = -1  # Use most powerful model
        elif priority == Priority.BALANCED:
            model_index = min(1, len(profile.models) - 1)  # Use middle tier
        
        return {
            "api": api_name,
            "model": profile.models[model_index],
            "estimated_latency": profile.avg_latency,
            "estimated_cost_per_1k": profile.cost_per_1k_tokens,
            "reason": f"Optimal for {task_type.value} with {priority.value} priority"
        }
    
    def get_fastest_api(self) -> str:
        """Get the fastest API based on current metrics"""
        return min(self.api_profiles.items(), 
                  key=lambda x: x[1].avg_latency)[0]
    
    def get_cheapest_api(self) -> str:
        """Get the cheapest API based on current pricing"""
        return min(self.api_profiles.items(), 
                  key=lambda x: x[1].cost_per_1k_tokens)[0]
    
    def get_most_reliable_api(self) -> str:
        """Get the most reliable API based on historical performance"""
        return max(self.api_profiles.items(), 
                  key=lambda x: x[1].reliability_score)[0]
    
    def update_performance_metrics(self, api_name: str, latency: float, success: bool):
        """Update performance metrics based on actual results"""
        if api_name not in self.performance_history:
            self.performance_history[api_name] = {
                "total_calls": 0,
                "successful_calls": 0,
                "total_latency": 0
            }
        
        history = self.performance_history[api_name]
        history["total_calls"] += 1
        if success:
            history["successful_calls"] += 1
            history["total_latency"] += latency
        
        # Update profile with real data
        if history["successful_calls"] > 0:
            self.api_profiles[api_name].avg_latency = (
                history["total_latency"] / history["successful_calls"]
            )
            self.api_profiles[api_name].reliability_score = (
                history["successful_calls"] / history["total_calls"]
            )
    
    def get_recommendation_report(self, task_type: TaskType, context_length: int = 0) -> str:
        """Generate a detailed recommendation report"""
        report = f"=== API Selection Report for {task_type.value} ===\n\n"
        
        for priority in Priority:
            selection = self.select_api_for_task(task_type, priority, context_length)
            report += f"{priority.value.upper()}:\n"
            report += f"  API: {selection['api']}\n"
            report += f"  Model: {selection['model']}\n"
            report += f"  Est. Latency: {selection.get('estimated_latency', 'N/A')}s\n"
            report += f"  Est. Cost/1K: ${selection.get('estimated_cost_per_1k', 'N/A')}\n"
            report += f"  Reason: {selection['reason']}\n\n"
        
        return report


# Example usage and testing
if __name__ == "__main__":
    selector = SmartAPISelector()
    
    # Test different scenarios
    print("Testing Smart API Selector\n" + "="*50)
    
    # Simple query - should use Gemini for speed
    result = selector.select_api_for_task(TaskType.SIMPLE_QUERY, Priority.SPEED)
    print(f"Simple Query (Speed): {result}\n")
    
    # Code generation - should use GPT-4 for quality
    result = selector.select_api_for_task(TaskType.CODE_GENERATION, Priority.QUALITY)
    print(f"Code Generation (Quality): {result}\n")
    
    # Long context - should use Gemini
    result = selector.select_api_for_task(TaskType.LONG_CONTEXT, Priority.BALANCED, context_length=500000)
    print(f"Long Context (500K tokens): {result}\n")
    
    # Get recommendations
    print(selector.get_recommendation_report(TaskType.COMPLEX_REASONING))
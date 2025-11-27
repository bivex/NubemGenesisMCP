"""
Task Optimizer - Intelligent model selection based on task requirements
Optimizes for cost, quality, and performance based on task analysis
"""

import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class TaskComplexity(Enum):
    SIMPLE = "simple"        # Basic queries, yes/no questions
    MODERATE = "moderate"    # Standard tasks, explanations
    COMPLEX = "complex"      # Multi-step reasoning, analysis
    EXPERT = "expert"        # Specialized knowledge, complex generation

class TaskCategory(Enum):
    # Content Generation
    GREETING = "greeting"
    SIMPLE_MATH = "simple_math"
    YES_NO_QUESTION = "yes_no_question"
    FACTUAL_QUERY = "factual_query"
    
    # Text Processing
    SUMMARIZATION = "summarization"
    TRANSLATION = "translation"
    EXPLANATION = "explanation"
    PROOFREADING = "proofreading"
    
    # Creative Tasks
    CREATIVE_WRITING = "creative_writing"
    STORYTELLING = "storytelling"
    POETRY = "poetry"
    
    # Technical Tasks
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    CODE_DEBUGGING = "code_debugging"
    ALGORITHM_DESIGN = "algorithm_design"
    
    # Analysis Tasks
    COMPLEX_REASONING = "complex_reasoning"
    DATA_ANALYSIS = "data_analysis"
    RESEARCH = "research"
    PROBLEM_SOLVING = "problem_solving"
    
    # Specialized
    VISION = "vision"
    LONG_CONTEXT = "long_context"
    REAL_TIME = "real_time"
    MULTI_TURN_CONVERSATION = "multi_turn_conversation"

@dataclass
class ModelProfile:
    """Profile for each model with capabilities and costs"""
    name: str
    provider: str
    complexity_range: Tuple[TaskComplexity, TaskComplexity]
    strengths: List[TaskCategory]
    weaknesses: List[TaskCategory]
    max_context: int
    cost_per_1k_input: float
    cost_per_1k_output: float
    avg_latency: float
    quality_score: float  # 0-1

class TaskOptimizer:
    """
    Optimizes model selection based on task requirements
    """
    
    def __init__(self):
        self.model_profiles = self._initialize_model_profiles()
        self.task_patterns = self._initialize_task_patterns()
        self.optimization_history = []
        
    def _initialize_model_profiles(self) -> Dict[str, ModelProfile]:
        """Initialize detailed model profiles"""
        return {
            # OpenAI Models
            "gpt-4": ModelProfile(
                name="gpt-4",
                provider="openai",
                complexity_range=(TaskComplexity.COMPLEX, TaskComplexity.EXPERT),
                strengths=[
                    TaskCategory.COMPLEX_REASONING,
                    TaskCategory.CODE_GENERATION,
                    TaskCategory.CREATIVE_WRITING,
                    TaskCategory.ALGORITHM_DESIGN
                ],
                weaknesses=[TaskCategory.REAL_TIME],
                max_context=8192,
                cost_per_1k_input=0.03,
                cost_per_1k_output=0.06,
                avg_latency=1.5,
                quality_score=0.95
            ),
            "gpt-4-turbo": ModelProfile(
                name="gpt-4-turbo",
                provider="openai",
                complexity_range=(TaskComplexity.MODERATE, TaskComplexity.EXPERT),
                strengths=[
                    TaskCategory.CODE_GENERATION,
                    TaskCategory.LONG_CONTEXT,
                    TaskCategory.DATA_ANALYSIS
                ],
                weaknesses=[TaskCategory.REAL_TIME],
                max_context=128000,
                cost_per_1k_input=0.01,
                cost_per_1k_output=0.03,
                avg_latency=1.2,
                quality_score=0.93
            ),
            "gpt-3.5-turbo": ModelProfile(
                name="gpt-3.5-turbo",
                provider="openai",
                complexity_range=(TaskComplexity.SIMPLE, TaskComplexity.MODERATE),
                strengths=[
                    TaskCategory.SUMMARIZATION,
                    TaskCategory.TRANSLATION,
                    TaskCategory.EXPLANATION,
                    TaskCategory.MULTI_TURN_CONVERSATION
                ],
                weaknesses=[TaskCategory.COMPLEX_REASONING, TaskCategory.ALGORITHM_DESIGN],
                max_context=16385,
                cost_per_1k_input=0.0015,
                cost_per_1k_output=0.002,
                avg_latency=0.8,
                quality_score=0.80
            ),
            
            # Anthropic Models
            "claude-3-opus": ModelProfile(
                name="claude-3-opus",
                provider="anthropic",
                complexity_range=(TaskComplexity.COMPLEX, TaskComplexity.EXPERT),
                strengths=[
                    TaskCategory.COMPLEX_REASONING,
                    TaskCategory.RESEARCH,
                    TaskCategory.CODE_REVIEW,
                    TaskCategory.PROBLEM_SOLVING
                ],
                weaknesses=[TaskCategory.REAL_TIME, TaskCategory.VISION],
                max_context=200000,
                cost_per_1k_input=0.015,
                cost_per_1k_output=0.075,
                avg_latency=1.3,
                quality_score=0.94
            ),
            "claude-3-sonnet": ModelProfile(
                name="claude-3-sonnet",
                provider="anthropic",
                complexity_range=(TaskComplexity.MODERATE, TaskComplexity.COMPLEX),
                strengths=[
                    TaskCategory.CODE_GENERATION,
                    TaskCategory.DATA_ANALYSIS,
                    TaskCategory.EXPLANATION
                ],
                weaknesses=[TaskCategory.VISION],
                max_context=200000,
                cost_per_1k_input=0.003,
                cost_per_1k_output=0.015,
                avg_latency=0.9,
                quality_score=0.88
            ),
            "claude-3-haiku": ModelProfile(
                name="claude-3-haiku-20240307",
                provider="anthropic",
                complexity_range=(TaskComplexity.SIMPLE, TaskComplexity.MODERATE),
                strengths=[
                    TaskCategory.SIMPLE_MATH,
                    TaskCategory.FACTUAL_QUERY,
                    TaskCategory.TRANSLATION,
                    TaskCategory.PROOFREADING
                ],
                weaknesses=[TaskCategory.CREATIVE_WRITING, TaskCategory.COMPLEX_REASONING],
                max_context=200000,
                cost_per_1k_input=0.00025,
                cost_per_1k_output=0.00125,
                avg_latency=0.6,
                quality_score=0.75
            ),
            
            # Google Models
            "gemini-1.5-pro": ModelProfile(
                name="gemini-1.5-pro",
                provider="google",
                complexity_range=(TaskComplexity.MODERATE, TaskComplexity.COMPLEX),
                strengths=[
                    TaskCategory.LONG_CONTEXT,
                    TaskCategory.VISION,
                    TaskCategory.DATA_ANALYSIS,
                    TaskCategory.RESEARCH
                ],
                weaknesses=[],
                max_context=1000000,
                cost_per_1k_input=0.00035,
                cost_per_1k_output=0.0014,
                avg_latency=0.7,
                quality_score=0.90
            ),
            "gemini-1.5-flash": ModelProfile(
                name="gemini-1.5-flash",
                provider="google",
                complexity_range=(TaskComplexity.SIMPLE, TaskComplexity.MODERATE),
                strengths=[
                    TaskCategory.REAL_TIME,
                    TaskCategory.GREETING,
                    TaskCategory.SIMPLE_MATH,
                    TaskCategory.YES_NO_QUESTION,
                    TaskCategory.VISION
                ],
                weaknesses=[TaskCategory.COMPLEX_REASONING],
                max_context=1000000,
                cost_per_1k_input=0.00001,
                cost_per_1k_output=0.00002,
                avg_latency=0.45,
                quality_score=0.70
            ),
            "gemini-2.0-flash": ModelProfile(
                name="gemini-2.0-flash",
                provider="google",
                complexity_range=(TaskComplexity.SIMPLE, TaskComplexity.MODERATE),
                strengths=[
                    TaskCategory.REAL_TIME,
                    TaskCategory.VISION,
                    TaskCategory.MULTI_TURN_CONVERSATION
                ],
                weaknesses=[TaskCategory.COMPLEX_REASONING],
                max_context=1000000,
                cost_per_1k_input=0.00001,
                cost_per_1k_output=0.00002,
                avg_latency=0.40,
                quality_score=0.72
            ),
        }
    
    def _initialize_task_patterns(self) -> Dict[TaskCategory, List[str]]:
        """Initialize patterns to detect task categories"""
        return {
            TaskCategory.GREETING: [
                r"^(hi|hello|hey|good\s+(morning|afternoon|evening))",
                r"how are you",
                r"what's up"
            ],
            TaskCategory.SIMPLE_MATH: [
                r"\d+\s*[\+\-\*\/]\s*\d+",
                r"calculate",
                r"what is \d+ (plus|minus|times|divided)",
                r"solve.*equation"
            ],
            TaskCategory.YES_NO_QUESTION: [
                r"^(is|are|do|does|did|will|would|should|can|could)",
                r"yes or no",
                r"true or false"
            ],
            TaskCategory.CODE_GENERATION: [
                r"write.*function",
                r"create.*class",
                r"implement",
                r"code.*that",
                r"program",
                r"script"
            ],
            TaskCategory.CODE_DEBUGGING: [
                r"debug",
                r"fix.*error",
                r"why.*not work",
                r"error.*code",
                r"bug.*in"
            ],
            TaskCategory.TRANSLATION: [
                r"translate",
                r"in (spanish|french|german|chinese|japanese)",
                r"how do you say",
                r"what is.*in.*language"
            ],
            TaskCategory.SUMMARIZATION: [
                r"summarize",
                r"summary",
                r"main points",
                r"key takeaways",
                r"tldr"
            ],
            TaskCategory.CREATIVE_WRITING: [
                r"write.*story",
                r"create.*poem",
                r"creative",
                r"imagine",
                r"fiction"
            ],
            TaskCategory.COMPLEX_REASONING: [
                r"analyze",
                r"compare.*contrast",
                r"evaluate",
                r"critical.*thinking",
                r"pros.*cons"
            ],
        }
    
    def detect_task_category(self, prompt: str) -> TaskCategory:
        """Detect the category of a task based on the prompt"""
        prompt_lower = prompt.lower()
        
        # Check each pattern
        for category, patterns in self.task_patterns.items():
            for pattern in patterns:
                if re.search(pattern, prompt_lower):
                    logger.debug(f"Detected task category: {category.value}")
                    return category
        
        # Default categories based on length and complexity
        if len(prompt) < 50:
            return TaskCategory.SIMPLE_MATH if any(c.isdigit() for c in prompt) else TaskCategory.FACTUAL_QUERY
        elif len(prompt) > 1000:
            return TaskCategory.LONG_CONTEXT
        else:
            return TaskCategory.EXPLANATION
    
    def assess_complexity(self, prompt: str, context_length: int = 0) -> TaskComplexity:
        """Assess the complexity of a task"""
        # Factors that increase complexity
        complexity_score = 0
        
        # Length factor
        if len(prompt) < 50:
            complexity_score += 0
        elif len(prompt) < 200:
            complexity_score += 1
        elif len(prompt) < 500:
            complexity_score += 2
        else:
            complexity_score += 3
        
        # Context factor
        if context_length > 10000:
            complexity_score += 2
        elif context_length > 1000:
            complexity_score += 1
        
        # Keyword factors
        complex_keywords = ["analyze", "evaluate", "compare", "design", "architect", "optimize", "research"]
        if any(keyword in prompt.lower() for keyword in complex_keywords):
            complexity_score += 2
        
        simple_keywords = ["what is", "define", "yes or no", "true or false", "how many"]
        if any(keyword in prompt.lower() for keyword in simple_keywords):
            complexity_score -= 1
        
        # Determine complexity level
        if complexity_score <= 1:
            return TaskComplexity.SIMPLE
        elif complexity_score <= 3:
            return TaskComplexity.MODERATE
        elif complexity_score <= 5:
            return TaskComplexity.COMPLEX
        else:
            return TaskComplexity.EXPERT
    
    def select_optimal_model(self,
                           prompt: str,
                           context_length: int = 0,
                           priority: str = "balanced",
                           max_cost: float = None,
                           min_quality: float = None,
                           required_context: int = None) -> Dict[str, Any]:
        """
        Select the optimal model for a given task
        
        Args:
            prompt: The task prompt
            context_length: Length of context in tokens
            priority: "speed", "cost", "quality", or "balanced"
            max_cost: Maximum acceptable cost per 1k tokens
            min_quality: Minimum quality score required (0-1)
            required_context: Minimum context window required
            
        Returns:
            Dict with selected model and reasoning
        """
        # Detect task category and complexity
        category = self.detect_task_category(prompt)
        complexity = self.assess_complexity(prompt, context_length)
        
        # Filter models based on requirements
        suitable_models = []
        
        for model_name, profile in self.model_profiles.items():
            # Check context requirements
            if required_context and profile.max_context < required_context:
                continue
            
            # Check cost constraints
            if max_cost and profile.cost_per_1k_output > max_cost:
                continue
            
            # Check quality requirements
            if min_quality and profile.quality_score < min_quality:
                continue
            
            # Check complexity match
            min_complex, max_complex = profile.complexity_range
            if not (min_complex.value <= complexity.value <= max_complex.value):
                continue
            
            # Check if model is good for this category
            score = 0
            if category in profile.strengths:
                score += 2
            elif category not in profile.weaknesses:
                score += 1
            else:
                score -= 1
            
            # Adjust score based on priority
            if priority == "speed":
                score -= profile.avg_latency
            elif priority == "cost":
                score -= (profile.cost_per_1k_input + profile.cost_per_1k_output) * 10
            elif priority == "quality":
                score += profile.quality_score * 5
            else:  # balanced
                score += profile.quality_score * 2
                score -= profile.avg_latency
                score -= (profile.cost_per_1k_input + profile.cost_per_1k_output) * 5
            
            suitable_models.append((model_name, profile, score))
        
        if not suitable_models:
            # Fallback to cheapest model
            return {
                "model": "gemini-1.5-flash",
                "provider": "google",
                "reason": "No models meet all constraints, using fastest/cheapest",
                "task_category": category.value,
                "complexity": complexity.value,
                "estimated_cost": 0.00003
            }
        
        # Sort by score and select best
        suitable_models.sort(key=lambda x: x[2], reverse=True)
        best_model_name, best_profile, score = suitable_models[0]
        
        # Calculate estimated cost
        estimated_tokens = len(prompt) // 4 + 200  # Rough estimate
        estimated_cost = (
            (estimated_tokens / 1000) * best_profile.cost_per_1k_input +
            (200 / 1000) * best_profile.cost_per_1k_output
        )
        
        # Log the decision
        decision = {
            "model": best_model_name,
            "provider": best_profile.provider,
            "reason": self._generate_reason(category, complexity, priority, best_profile),
            "task_category": category.value,
            "complexity": complexity.value,
            "estimated_cost": round(estimated_cost, 6),
            "estimated_latency": best_profile.avg_latency,
            "quality_score": best_profile.quality_score,
            "alternatives": [m[0] for m in suitable_models[1:4]]  # Top 3 alternatives
        }
        
        self.optimization_history.append({
            "timestamp": time.time(),
            "prompt_preview": prompt[:100],
            "decision": decision
        })
        
        return decision
    
    def _generate_reason(self, category: TaskCategory, complexity: TaskComplexity, 
                        priority: str, profile: ModelProfile) -> str:
        """Generate a human-readable reason for the model selection"""
        reasons = []
        
        if category in profile.strengths:
            reasons.append(f"excellent for {category.value}")
        
        if complexity == TaskComplexity.SIMPLE and profile.avg_latency < 0.5:
            reasons.append("fast for simple tasks")
        elif complexity == TaskComplexity.EXPERT and profile.quality_score > 0.9:
            reasons.append("high quality for expert tasks")
        
        if priority == "speed" and profile.avg_latency < 0.6:
            reasons.append("optimized for speed")
        elif priority == "cost" and profile.cost_per_1k_output < 0.002:
            reasons.append("cost-effective")
        elif priority == "quality" and profile.quality_score > 0.85:
            reasons.append("high quality output")
        
        return "; ".join(reasons) if reasons else "best match for requirements"
    
    def get_optimization_report(self) -> Dict[str, Any]:
        """Generate optimization report from history"""
        if not self.optimization_history:
            return {"message": "No optimization history available"}
        
        # Analyze history
        model_usage = {}
        category_usage = {}
        total_estimated_cost = 0
        
        for entry in self.optimization_history:
            decision = entry["decision"]
            model = decision["model"]
            category = decision["task_category"]
            
            model_usage[model] = model_usage.get(model, 0) + 1
            category_usage[category] = category_usage.get(category, 0) + 1
            total_estimated_cost += decision["estimated_cost"]
        
        return {
            "total_optimizations": len(self.optimization_history),
            "model_distribution": model_usage,
            "category_distribution": category_usage,
            "total_estimated_cost": round(total_estimated_cost, 4),
            "avg_cost_per_request": round(total_estimated_cost / len(self.optimization_history), 6),
            "recommendations": self._generate_recommendations(model_usage, category_usage)
        }
    
    def _generate_recommendations(self, model_usage: Dict, category_usage: Dict) -> List[str]:
        """Generate optimization recommendations based on usage"""
        recommendations = []
        
        # Check if using expensive models too often
        expensive_models = ["gpt-4", "claude-3-opus"]
        expensive_usage = sum(model_usage.get(m, 0) for m in expensive_models)
        if expensive_usage > len(self.optimization_history) * 0.3:
            recommendations.append("Consider using cheaper models for simple tasks to reduce costs")
        
        # Check if categories align with model strengths
        if "code_generation" in category_usage and category_usage["code_generation"] > 5:
            if model_usage.get("gpt-4", 0) < category_usage["code_generation"] * 0.5:
                recommendations.append("Use GPT-4 more for code generation tasks for better quality")
        
        # Check for long context usage
        if "long_context" in category_usage and model_usage.get("gemini-1.5-pro", 0) == 0:
            recommendations.append("Consider Gemini 1.5 Pro for long context tasks (up to 1M tokens)")
        
        return recommendations

import time

if __name__ == "__main__":
    # Test the task optimizer
    optimizer = TaskOptimizer()
    
    print("Testing Task Optimizer\n" + "="*50)
    
    test_prompts = [
        ("Hi there!", "speed"),
        ("What is 2+2?", "cost"),
        ("Write a function to sort an array using quicksort", "quality"),
        ("Analyze the pros and cons of microservices architecture", "balanced"),
        ("Translate 'Hello World' to Spanish", "cost"),
        ("Debug this code: def sum(a,b): return a+b+c", "quality"),
    ]
    
    for prompt, priority in test_prompts:
        result = optimizer.select_optimal_model(prompt, priority=priority)
        print(f"\nPrompt: '{prompt[:50]}...'")
        print(f"Priority: {priority}")
        print(f"Selected: {result['model']} ({result['provider']})")
        print(f"Reason: {result['reason']}")
        print(f"Category: {result['task_category']}, Complexity: {result['complexity']}")
        print(f"Est. Cost: ${result['estimated_cost']:.6f}, Latency: {result['estimated_latency']}s")
    
    # Show optimization report
    report = optimizer.get_optimization_report()
    print(f"\nOptimization Report:")
    print(f"Total requests: {report['total_optimizations']}")
    print(f"Total cost: ${report['total_estimated_cost']:.4f}")
    print(f"Recommendations: {report['recommendations']}")
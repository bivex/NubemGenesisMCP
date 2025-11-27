#!/usr/bin/env python3
"""
Complexity Evaluator for Trinity Router
Evaluates query complexity to determine if single persona or swarm is needed
NO LLM required - uses heuristics and pattern matching
"""

import re
from typing import Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ComplexityLevel(Enum):
    """Complexity levels for queries"""
    TRIVIAL = "trivial"      # 0.0-0.2: Simple fixes, one-liners
    SIMPLE = "simple"         # 0.2-0.4: Standard tasks, single focus
    MODERATE = "moderate"     # 0.4-0.6: Multiple steps, some depth
    COMPLEX = "complex"       # 0.6-0.8: Multi-faceted, requires expertise
    EXPERT = "expert"         # 0.8-1.0: Architecture, critical systems


@dataclass
class ComplexityAnalysis:
    """Result of complexity evaluation"""
    score: float  # 0.0-1.0
    level: ComplexityLevel
    factors: Dict[str, float]  # Individual complexity factors
    recommended_personas: int  # How many personas to use
    reasoning: List[str]  # Human-readable reasoning
    requires_rag: bool  # Whether RAG context would help
    estimated_time_seconds: int  # Estimated processing time


class ComplexityEvaluator:
    """
    Evaluates query complexity using multiple heuristics
    Fast, deterministic scoring without LLM calls
    """

    # Complexity factor weights (FIX BUG #1: Rebalanced for better detection)
    FACTOR_WEIGHTS = {
        "query_length": 0.09,      # Reduced: length alone doesn't mean complex
        "technical_terms": 0.25,   # Increased: technical depth is critical
        "multi_step": 0.20,        # Increased: multi-step = more complex
        "code_size": 0.10,         # Same: code size matters
        "architectural": 0.25,     # Increased: architecture queries are complex
        "integration": 0.05,       # Reduced: less critical than architecture
        "production_critical": 0.03, # Reduced: minor factor
        "ambiguity": 0.02,         # Reduced: minor factor
        "analysis_request": 0.06,  # NEW: Queries asking for analysis/explanation
    }

    # Patterns indicating complexity (FIX BUG #1: Added bullet points)
    MULTI_STEP_PATTERNS = [
        r"(first|then|next|after|before|finally)",
        r"(step \d+|phase \d+|\d+\)|\d+\.)",
        r"(and then|followed by|subsequently)",
        r"^[\s]*[-*+]\s",  # Bullet points (-, *, +)
        r"\n[\s]*[-*+]\s",  # Bullet points on new lines
    ]

    ARCHITECTURAL_KEYWORDS = [
        # Core architecture terms
        "architecture", "design", "system design", "scalable", "distributed",
        "microservices", "high availability", "fault tolerant",
        "load balancing", "sharding", "caching strategy",

        # Container & orchestration
        "kubernetes", "docker", "containers", "service mesh", "orchestration",
        "k8s", "pod", "deployment", "helm", "istio",

        # Security architecture
        "audit", "audit system", "security audit", "comprehensive",
        "penetration testing", "vulnerability scanning", "compliance",
        "security system", "security infrastructure", "zero trust",

        # Cloud platforms (FIX BUG #1: Added cloud providers)
        "aws", "azure", "gcp", "google cloud", "cloud platform",
        "multi-cloud", "hybrid cloud", "cloud native",

        # Additional architectural indicators
        "automated", "failover", "redundancy", "observability",
        "multi-service", "multi-tier", "layered architecture",

        # Design patterns & quality attributes (FIX BUG #1: Added)
        "event-driven", "cqrs", "saga pattern", "circuit breaker",
        "api gateway", "bff", "strangler pattern",
        "resilience", "elasticity", "maintainability"
    ]

    INTEGRATION_KEYWORDS = [
        "integrate", "connect", "combine", "merge", "coordinate",
        "synchronize", "orchestrate", "api gateway", "message queue"
    ]

    PRODUCTION_KEYWORDS = [
        "production", "enterprise", "mission critical", "downtime",
        "sla", "reliability", "monitoring", "disaster recovery"
    ]

    AMBIGUOUS_INDICATORS = [
        "somehow", "maybe", "not sure", "confused", "don't know",
        "any way", "whatever works", "figure out"
    ]

    # Technical term categories (FIX BUG #1: Expanded with more terms + architecture category)
    TECHNICAL_TERMS = {
        "advanced_cs": ["algorithm", "complexity", "optimization", "heuristic", "graph theory",
                       "data structure", "time complexity", "space complexity", "big-o"],
        "distributed": ["consensus", "raft", "paxos", "eventual consistency", "cap theorem",
                       "distributed system", "partition tolerance", "vector clock"],
        "security": ["encryption", "authentication", "authorization", "certificate", "penetration",
                    "oauth", "jwt", "ssl/tls", "rbac", "vulnerability", "exploit",
                    "security audit", "compliance", "threat detection", "vulnerability scanning",
                    "penetration testing", "real-time threat"],
        "performance": ["latency", "throughput", "bottleneck", "profiling", "benchmark",
                       "optimize", "optimization", "performance tuning", "caching",
                       "memory leak", "cpu usage", "response time", "performance implications"],
        "data": ["normalization", "indexing", "partitioning", "replication", "sharding",
                "transaction", "acid", "nosql", "relational", "query optimization",
                "database design", "schema", "migration", "sql", "database", "query"],
        "devops": ["ci/cd", "pipeline", "jenkins", "gitlab", "terraform",
                  "ansible", "deployment", "rollback", "blue-green", "canary"],
        "architecture": ["microservices", "scalable", "architecture", "distributed",
                        "high availability", "fault tolerant", "load balancing",
                        "service mesh", "api gateway", "event-driven", "cqrs",
                        "kubernetes", "docker", "cloud", "aws", "gcp", "azure"],
    }

    def __init__(self):
        """Initialize complexity evaluator"""
        self.evaluation_cache = {}

    def evaluate(self, query: str, domain_analysis=None) -> ComplexityAnalysis:
        """
        Evaluate query complexity

        Args:
            query: User query string
            domain_analysis: Optional DomainAnalysis object for context

        Returns:
            ComplexityAnalysis object with score and recommendations
        """
        # Check cache
        cache_key = query.lower().strip()
        if cache_key in self.evaluation_cache:
            logger.debug(f"Cache hit for complexity evaluation")
            return self.evaluation_cache[cache_key]

        # Calculate individual complexity factors
        factors = self._calculate_factors(query, domain_analysis)

        # Calculate weighted score
        score = self._calculate_weighted_score(factors)

        # Determine complexity level
        level = self._determine_level(score)

        # Recommend number of personas
        recommended_personas = self._recommend_personas(score, factors)

        # Check if RAG would help
        requires_rag = self._check_rag_requirement(query, factors)

        # Generate reasoning
        reasoning = self._generate_reasoning(factors, score)

        # Estimate processing time
        estimated_time = self._estimate_time(score, recommended_personas)

        result = ComplexityAnalysis(
            score=score,
            level=level,
            factors=factors,
            recommended_personas=recommended_personas,
            reasoning=reasoning,
            requires_rag=requires_rag,
            estimated_time_seconds=estimated_time
        )

        # Cache result
        self.evaluation_cache[cache_key] = result

        logger.info(f"Complexity: {level.value} ({score:.2f}) - {recommended_personas} personas")
        return result

    def _calculate_factors(self, query: str, domain_analysis) -> Dict[str, float]:
        """Calculate individual complexity factors (0-1 scale)"""
        factors = {}

        query_lower = query.lower()

        # 1. Query length (longer = more complex)
        factors["query_length"] = self._score_query_length(query)

        # 2. Technical terms (more advanced terms = higher complexity)
        factors["technical_terms"] = self._score_technical_terms(query_lower)

        # 3. Multi-step indicators
        factors["multi_step"] = self._score_multi_step(query_lower)

        # 4. Code size (if code present)
        factors["code_size"] = self._score_code_size(query)

        # 5. Architectural complexity
        factors["architectural"] = self._score_architectural(query_lower)

        # 6. Integration complexity
        factors["integration"] = self._score_integration(query_lower)

        # 7. Production criticality
        factors["production_critical"] = self._score_production(query_lower)

        # 8. Ambiguity (higher = needs more clarification)
        factors["ambiguity"] = self._score_ambiguity(query_lower)

        # 9. Analysis request (FIX BUG #1: Queries asking for analysis/explanation)
        factors["analysis_request"] = self._score_analysis_request(query_lower)

        return factors

    def _score_query_length(self, query: str) -> float:
        """Score based on query length"""
        words = len(query.split())
        if words < 5:
            return 0.1
        elif words < 10:
            return 0.4
        elif words < 20:
            return 0.6
        elif words < 40:
            return 0.8
        else:
            return 1.0

    def _score_technical_terms(self, query_lower: str) -> float:
        """Score based on technical term density"""
        total_terms = 0
        advanced_terms = 0

        for category, terms in self.TECHNICAL_TERMS.items():
            for term in terms:
                if term in query_lower:
                    total_terms += 1
                    # FIX BUG #1: Added architecture to advanced categories
                    if category in ["distributed", "advanced_cs", "security", "architecture"]:
                        advanced_terms += 1

        if total_terms == 0:
            return 0.2
        elif total_terms < 3:
            return 0.4
        elif advanced_terms > 0:
            return 0.8
        else:
            return 0.6

    def _score_multi_step(self, query_lower: str) -> float:
        """Score based on multi-step indicators"""
        step_count = 0

        for pattern in self.MULTI_STEP_PATTERNS:
            matches = re.findall(pattern, query_lower, re.IGNORECASE)
            step_count += len(matches)

        # Check for numbered lists
        numbered_steps = len(re.findall(r'\d+[\.\)]', query_lower))
        step_count += numbered_steps

        if step_count == 0:
            return 0.1
        elif step_count < 3:
            return 0.4
        elif step_count < 6:
            return 0.7
        else:
            return 0.9

    def _score_code_size(self, query: str) -> float:
        """Score based on code block size"""
        # Count lines that look like code
        code_lines = 0
        for line in query.split('\n'):
            # Simple heuristic: lines with indentation or special chars
            if line.strip() and (
                line.startswith(' ' * 2) or
                line.startswith('\t') or
                re.search(r'[{}\[\]();=]', line)
            ):
                code_lines += 1

        if code_lines == 0:
            return 0.0
        elif code_lines < 10:
            return 0.3
        elif code_lines < 50:
            return 0.6
        else:
            return 0.9

    def _score_architectural(self, query_lower: str) -> float:
        """Score based on architectural keywords"""
        matches = sum(1 for kw in self.ARCHITECTURAL_KEYWORDS if kw in query_lower)

        if matches == 0:
            return 0.0
        elif matches == 1:
            return 0.4
        elif matches == 2:
            return 0.6
        elif matches == 3:
            return 0.8
        elif matches == 4:
            return 0.95
        else:
            return 1.0

    def _score_integration(self, query_lower: str) -> float:
        """Score based on integration complexity"""
        matches = sum(1 for kw in self.INTEGRATION_KEYWORDS if kw in query_lower)

        if matches == 0:
            return 0.0
        elif matches < 2:
            return 0.5
        else:
            return 0.8

    def _score_production(self, query_lower: str) -> float:
        """Score based on production criticality"""
        matches = sum(1 for kw in self.PRODUCTION_KEYWORDS if kw in query_lower)

        if matches == 0:
            return 0.0
        elif matches < 2:
            return 0.6
        else:
            return 0.9

    def _score_ambiguity(self, query_lower: str) -> float:
        """Score based on ambiguity indicators"""
        matches = sum(1 for ind in self.AMBIGUOUS_INDICATORS if ind in query_lower)

        return min(matches * 0.3, 1.0)

    def _score_analysis_request(self, query_lower: str) -> float:
        """Score based on analysis/explanation requests (FIX BUG #1: Added)"""
        analysis_keywords = [
            "explain", "analyze", "analysis", "why", "how does", "what causes",
            "describe", "compare", "evaluate", "assess", "review",
            "implications", "impact", "consequences", "trade-offs"
        ]

        matches = sum(1 for kw in analysis_keywords if kw in query_lower)

        if matches == 0:
            return 0.0
        elif matches == 1:
            return 0.5
        else:
            return 0.9

    def _calculate_weighted_score(self, factors: Dict[str, float]) -> float:
        """Calculate weighted complexity score"""
        total_score = 0.0

        for factor_name, factor_score in factors.items():
            weight = self.FACTOR_WEIGHTS.get(factor_name, 0.0)
            total_score += factor_score * weight

        # Normalize to 0-1 range
        return min(max(total_score, 0.0), 1.0)

    def _determine_level(self, score: float) -> ComplexityLevel:
        """Determine complexity level from score (FIX BUG #1: Adjusted thresholds)"""
        if score < 0.25:
            return ComplexityLevel.TRIVIAL
        elif score < 0.45:
            return ComplexityLevel.SIMPLE
        elif score < 0.65:
            return ComplexityLevel.MODERATE
        elif score < 0.85:
            return ComplexityLevel.COMPLEX
        else:
            return ComplexityLevel.EXPERT

    def _recommend_personas(self, score: float, factors: Dict[str, float]) -> int:
        """Recommend number of personas based on complexity (FIX BUG #1: Aligned with new thresholds)"""
        if score < 0.35:
            return 1  # Simple queries: single persona
        elif score < 0.55:
            return 2  # Moderate: 2 personas for validation
        elif score < 0.75:
            return 3  # Complex: 3 personas for diverse perspectives
        else:
            return 5  # Expert: full swarm for critical tasks

    def _check_rag_requirement(self, query: str, factors: Dict[str, float]) -> bool:
        """Check if RAG context would help"""
        rag_indicators = [
            "previous", "last time", "before", "history",
            "continue", "based on", "remember", "context"
        ]

        query_lower = query.lower()
        has_indicators = any(ind in query_lower for ind in rag_indicators)

        # Also recommend RAG for high ambiguity
        high_ambiguity = factors.get("ambiguity", 0) > 0.5

        return has_indicators or high_ambiguity

    def _generate_reasoning(self, factors: Dict[str, float], score: float) -> List[str]:
        """Generate human-readable reasoning"""
        reasoning = []

        # Identify top contributing factors
        sorted_factors = sorted(factors.items(), key=lambda x: x[1], reverse=True)

        for factor_name, factor_score in sorted_factors[:3]:
            if factor_score > 0.5:
                reasoning.append(self._factor_to_reason(factor_name, factor_score))

        # Add overall assessment
        if score < 0.3:
            reasoning.append("Query is straightforward, single persona recommended")
        elif score < 0.6:
            reasoning.append("Moderate complexity, multiple perspectives beneficial")
        else:
            reasoning.append("High complexity, full swarm analysis recommended")

        return reasoning

    def _factor_to_reason(self, factor_name: str, score: float) -> str:
        """Convert factor to human-readable reason"""
        reasons = {
            "query_length": "Query is detailed and comprehensive",
            "technical_terms": "Contains advanced technical concepts",
            "multi_step": "Requires multiple sequential steps",
            "code_size": "Involves significant code review/generation",
            "architectural": "Architectural design considerations present",
            "integration": "Requires integration of multiple systems",
            "production_critical": "Production/enterprise requirements detected",
            "ambiguity": "Query has some ambiguity requiring clarification",
        }
        return reasons.get(factor_name, f"{factor_name} factor detected")

    def _estimate_time(self, score: float, personas: int) -> int:
        """Estimate processing time in seconds"""
        # Base time per persona
        base_time = 2  # seconds

        # Complexity multiplier
        complexity_multiplier = 1 + score

        # Calculate total
        total_time = int(base_time * personas * complexity_multiplier)

        return max(total_time, 1)  # At least 1 second


# Convenience function
def evaluate_complexity(query: str, domain_analysis=None) -> ComplexityAnalysis:
    """Evaluate complexity for a query (convenience function)"""
    evaluator = ComplexityEvaluator()
    return evaluator.evaluate(query, domain_analysis)


if __name__ == "__main__":
    # Test cases
    test_queries = [
        "Fix typo in README",
        "Review my Python code for bugs",
        "Design a scalable microservices architecture on AWS with high availability",
        "Optimize this SQL query and explain the performance implications",
        """
        Create a production-ready Kubernetes deployment with:
        1. Auto-scaling
        2. Load balancing
        3. Monitoring
        4. Disaster recovery
        """,
    ]

    evaluator = ComplexityEvaluator()
    for query in test_queries:
        result = evaluator.evaluate(query)
        print(f"\n{'='*60}")
        print(f"Query: {query[:80]}...")
        print(f"Complexity: {result.level.value} ({result.score:.2f})")
        print(f"Personas recommended: {result.recommended_personas}")
        print(f"Requires RAG: {result.requires_rag}")
        print(f"Estimated time: {result.estimated_time_seconds}s")
        print(f"Reasoning:")
        for reason in result.reasoning:
            print(f"  - {reason}")

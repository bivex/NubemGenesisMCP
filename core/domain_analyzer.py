#!/usr/bin/env python3
"""
Domain Analyzer for Trinity Router
Detects technical domain and task type from user queries
NO LLM required - uses keyword matching + regex patterns
"""

import re
from typing import Dict, List, Tuple, Set
from collections import defaultdict
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class DomainAnalysis:
    """Result of domain analysis"""
    primary_domain: str
    secondary_domain: str
    task_type: str
    confidence: float
    has_code: bool
    code_language: str
    keywords_matched: List[str]
    complexity_indicators: Dict[str, int]


class DomainAnalyzer:
    """
    Analyzes user queries to detect technical domain and task type
    Fast, deterministic, no LLM calls required
    """

    # Domain keyword mappings
    DOMAIN_KEYWORDS = {
        # Programming Languages
        "python": ["python", "py", "django", "flask", "fastapi", "pytest", "pandas", "numpy", "pip", "virtualenv"],
        "javascript": ["javascript", "js", "node", "react", "vue", "angular", "typescript", "ts", "npm", "webpack"],
        "java": ["java", "spring", "maven", "gradle", "junit", "jvm", "jar"],
        "go": ["golang", "go", "goroutine", "go mod"],
        "rust": ["rust", "cargo", "rustc"],
        "cpp": ["c++", "cpp", "cmake"],

        # Development Areas
        "backend": ["api", "rest", "graphql", "endpoint", "server", "backend", "microservices", "grpc"],
        "frontend": ["ui", "ux", "component", "frontend", "css", "html", "dom", "browser"],
        "fullstack": ["fullstack", "full-stack", "monorepo", "webapp"],
        "mobile": ["ios", "android", "react native", "flutter", "swift", "kotlin"],

        # Databases
        "sql": ["sql", "mysql", "postgresql", "postgres", "database", "db", "query", "schema", "table"],
        "nosql": ["mongodb", "redis", "cassandra", "dynamodb", "nosql"],
        "vector": ["qdrant", "pinecone", "weaviate", "vector", "embedding", "similarity"],

        # Security
        "security": ["security", "vulnerability", "auth", "encrypt", "secure", "ssl", "tls", "certificate"],
        "penetration": ["pentest", "hack", "exploit", "vulnerability scan", "nmap"],

        # Infrastructure
        "devops": ["docker", "kubernetes", "k8s", "ci/cd", "pipeline", "deploy", "jenkins", "gitlab"],
        "cloud": ["aws", "gcp", "azure", "cloud", "serverless", "lambda", "cloud run"],
        "infrastructure": ["terraform", "ansible", "puppet", "chef", "infrastructure as code"],

        # Data & AI
        "data-science": ["ml", "machine learning", "model", "training", "dataset", "neural network"],
        "data-engineering": ["pipeline", "etl", "airflow", "spark", "kafka", "data warehouse"],
        "ai": ["ai", "artificial intelligence", "llm", "gpt", "claude", "prompt"],

        # Business & Product
        "product": ["feature", "user story", "roadmap", "prd", "requirement", "stakeholder"],
        "qa": ["test", "testing", "quality", "bug", "qa", "regression"],
        "management": ["project", "agile", "scrum", "sprint", "kanban", "jira"],
    }

    # Code detection patterns
    CODE_PATTERNS = {
        "python": r"(def\s+\w+|class\s+\w+|import\s+\w+|from\s+\w+|\.py\b|__init__|@\w+\()",
        "javascript": r"(function\s+\w+|const\s+\w+=|let\s+\w+=|var\s+\w+=|\.js\b|\.jsx\b|\.ts\b|=>)",
        "java": r"(public\s+class|private\s+\w+|@Override|\.java\b|System\.out)",
        "go": r"(func\s+\w+|package\s+\w+|import\s+\(|\.go\b)",
        "rust": r"(fn\s+\w+|let\s+mut|impl\s+\w+|\.rs\b)",
        "sql": r"(SELECT\s+|INSERT\s+INTO|UPDATE\s+|DELETE\s+FROM|CREATE\s+TABLE|WHERE\s+|JOIN\s+)",
        "dockerfile": r"(FROM\s+|RUN\s+|COPY\s+|CMD\s+|ENTRYPOINT\s+|EXPOSE\s+)",
        "yaml": r"(apiVersion:|kind:|metadata:|spec:|---)",
        "json": r'(\{[\s\S]*"[\w]+":\s*[\[\{"])',
    }

    # Task type keywords
    TASK_KEYWORDS = {
        "review": ["review", "analyze", "check", "audit", "evaluate", "inspect", "assess"],
        "design": ["design", "architect", "plan", "create schema", "model", "blueprint"],
        "debug": ["bug", "error", "fix", "debug", "issue", "problem", "broken", "doesn't work"],
        "optimize": ["optimize", "improve", "performance", "faster", "slow", "speed up", "bottleneck"],
        "implement": ["implement", "build", "create", "develop", "write", "code", "make"],
        "deploy": ["deploy", "setup", "configure", "install", "provision"],
        "test": ["test", "testing", "unit test", "integration test", "e2e", "pytest"],
        "refactor": ["refactor", "cleanup", "reorganize", "restructure", "clean code"],
        "document": ["document", "documentation", "readme", "explain", "comment"],
        "explain": ["explain", "how does", "what is", "why", "understand", "clarify"],
    }

    # Complexity indicators (higher = more complex)
    COMPLEXITY_INDICATORS = {
        "multi_step": ["step", "then", "after", "before", "sequence", "flow"],
        "integration": ["integrate", "connect", "combine", "merge", "coordinate"],
        "architecture": ["architecture", "system design", "scalable", "distributed"],
        "multiple_components": ["multiple", "several", "various", "different"],
        "production": ["production", "enterprise", "scale", "high availability", "mission critical"],
    }

    def __init__(self):
        """Initialize domain analyzer"""
        self.domain_cache = {}  # Cache for repeated queries

    def analyze(self, query: str) -> DomainAnalysis:
        """
        Analyze query and detect domain + task type

        Args:
            query: User query string

        Returns:
            DomainAnalysis object with detected information
        """
        # Check cache
        cache_key = query.lower().strip()
        if cache_key in self.domain_cache:
            logger.debug(f"Cache hit for query: {query[:50]}")
            return self.domain_cache[cache_key]

        query_lower = query.lower()

        # 1. Detect domains (score each domain by keyword matches)
        domain_scores = self._score_domains(query_lower)

        # 2. Detect code and language
        has_code, code_language = self._detect_code(query)

        # 3. Detect task type
        task_type = self._detect_task_type(query_lower)

        # 4. Calculate complexity indicators
        complexity_indicators = self._calculate_complexity(query_lower)

        # 5. Determine primary and secondary domains
        sorted_domains = sorted(domain_scores.items(), key=lambda x: x[1], reverse=True)
        primary_domain = sorted_domains[0][0] if sorted_domains else "general"
        secondary_domain = sorted_domains[1][0] if len(sorted_domains) > 1 else ""

        # 6. Calculate confidence (based on match strength)
        confidence = self._calculate_confidence(
            domain_scores[primary_domain] if primary_domain in domain_scores else 0,
            has_code,
            complexity_indicators
        )

        # 7. Get matched keywords
        keywords_matched = self._get_matched_keywords(query_lower, primary_domain)

        result = DomainAnalysis(
            primary_domain=primary_domain,
            secondary_domain=secondary_domain,
            task_type=task_type,
            confidence=confidence,
            has_code=has_code,
            code_language=code_language,
            keywords_matched=keywords_matched,
            complexity_indicators=complexity_indicators
        )

        # Cache result
        self.domain_cache[cache_key] = result

        logger.info(f"Domain analysis: {primary_domain} ({confidence:.2f}) - {task_type}")
        return result

    def _score_domains(self, query_lower: str) -> Dict[str, int]:
        """Score each domain based on keyword matches"""
        scores = defaultdict(int)

        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            for keyword in keywords:
                # Exact match gets full point
                if f" {keyword} " in f" {query_lower} ":
                    scores[domain] += 2
                # Partial match gets half point
                elif keyword in query_lower:
                    scores[domain] += 1

        return dict(scores)

    def _detect_code(self, query: str) -> Tuple[bool, str]:
        """Detect if query contains code and which language"""
        for language, pattern in self.CODE_PATTERNS.items():
            if re.search(pattern, query, re.MULTILINE | re.IGNORECASE):
                return True, language
        return False, ""

    def _detect_task_type(self, query_lower: str) -> str:
        """Detect the type of task user wants to perform"""
        task_scores = defaultdict(int)

        for task_type, keywords in self.TASK_KEYWORDS.items():
            for keyword in keywords:
                if keyword in query_lower:
                    task_scores[task_type] += 1

        if not task_scores:
            return "general"

        # Return task with highest score
        return max(task_scores.items(), key=lambda x: x[1])[0]

    def _calculate_complexity(self, query_lower: str) -> Dict[str, int]:
        """Calculate complexity indicators"""
        indicators = {}

        for indicator_type, keywords in self.COMPLEXITY_INDICATORS.items():
            count = sum(1 for keyword in keywords if keyword in query_lower)
            if count > 0:
                indicators[indicator_type] = count

        return indicators

    def _calculate_confidence(
        self,
        domain_score: int,
        has_code: bool,
        complexity_indicators: Dict[str, int]
    ) -> float:
        """Calculate confidence score (0-1)"""
        confidence = 0.5  # Base confidence

        # Domain match adds confidence
        if domain_score > 0:
            confidence += min(domain_score * 0.1, 0.3)

        # Code presence adds confidence
        if has_code:
            confidence += 0.15

        # Complexity indicators reduce confidence slightly (harder to categorize)
        complexity_count = sum(complexity_indicators.values())
        if complexity_count > 0:
            confidence -= min(complexity_count * 0.02, 0.1)

        return min(max(confidence, 0.0), 1.0)

    def _get_matched_keywords(self, query_lower: str, domain: str) -> List[str]:
        """Get list of keywords that matched for a domain"""
        if domain not in self.DOMAIN_KEYWORDS:
            return []

        matched = []
        for keyword in self.DOMAIN_KEYWORDS[domain]:
            if keyword in query_lower:
                matched.append(keyword)

        return matched[:5]  # Return top 5

    def get_domain_info(self, domain: str) -> Dict[str, any]:
        """Get information about a specific domain"""
        return {
            "domain": domain,
            "keywords": self.DOMAIN_KEYWORDS.get(domain, []),
            "description": self._get_domain_description(domain)
        }

    def _get_domain_description(self, domain: str) -> str:
        """Get human-readable description of domain"""
        descriptions = {
            "python": "Python programming and ecosystem",
            "javascript": "JavaScript/TypeScript development",
            "backend": "Backend API and server development",
            "frontend": "Frontend UI/UX development",
            "security": "Security and vulnerability assessment",
            "devops": "DevOps and CI/CD pipelines",
            "cloud": "Cloud infrastructure and services",
            "data-science": "Machine learning and data science",
            "sql": "SQL databases and queries",
            "nosql": "NoSQL databases",
        }
        return descriptions.get(domain, f"{domain} development")


# Convenience function
def analyze_domain(query: str) -> DomainAnalysis:
    """Analyze domain for a query (convenience function)"""
    analyzer = DomainAnalyzer()
    return analyzer.analyze(query)


if __name__ == "__main__":
    # Test cases
    test_queries = [
        "Review my Python code for bugs",
        "Design a scalable microservices architecture on AWS",
        "Fix this JavaScript function that doesn't work",
        "Optimize SQL query performance",
        "Create a React component for user profile",
    ]

    analyzer = DomainAnalyzer()
    for query in test_queries:
        result = analyzer.analyze(query)
        print(f"\nQuery: {query}")
        print(f"  Domain: {result.primary_domain} ({result.confidence:.2f})")
        print(f"  Task: {result.task_type}")
        print(f"  Has code: {result.has_code} ({result.code_language})")
        print(f"  Keywords: {', '.join(result.keywords_matched)}")

"""
Domain Analyzer for v6-auto-routing

Analyzes user queries to detect technical domain and task type.
Uses HYBRID approach: keyword matching + LLM fallback for precision.
"""

import re
import json
import os
from typing import Dict, List, Optional
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class DomainAnalyzer:
    """
    Analyzes user queries to detect domain and complexity.
    HYBRID: keyword matching (fast) + LLM fallback (precise).
    """

    def __init__(self, use_llm_fallback: bool = True, confidence_threshold: float = 0.6):
        """
        Initialize DomainAnalyzer.

        Args:
            use_llm_fallback: Enable LLM fallback for low-confidence results
            confidence_threshold: Minimum confidence to skip LLM (default: 0.6)
        """
        self.use_llm_fallback = use_llm_fallback
        self.confidence_threshold = confidence_threshold
        self._cache = {}  # Cache for common queries

    DOMAIN_KEYWORDS = {
        # Programming Languages
        "python": ["python", "py", "django", "flask", "fastapi", "pytest", "pandas", "numpy"],
        "javascript": ["javascript", "js", "node", "nodejs", "react", "vue", "angular", "typescript", "ts"],
        "java": ["java", "spring", "maven", "gradle", "junit"],
        "go": ["golang", "go"],
        "rust": ["rust", "cargo"],
        "cpp": ["c++", "cpp"],

        # Backend
        "backend": ["api", "rest", "graphql", "endpoint", "server", "backend", "microservice"],

        # Frontend
        "frontend": ["ui", "ux", "component", "frontend", "css", "html", "dom", "responsive"],

        # Database
        "database": ["database", "db", "sql", "query", "schema", "table", "postgresql", "mysql",
                     "mongodb", "redis", "nosql", "index", "migration"],

        # Security
        "security": ["security", "vulnerability", "auth", "authentication", "authorization",
                     "encrypt", "secure", "owasp", "xss", "csrf", "injection"],
        "penetration": ["pentest", "penetration test", "hack", "exploit", "vulnerability scan"],

        # Infrastructure & Cloud
        "devops": ["docker", "kubernetes", "k8s", "ci/cd", "pipeline", "deploy", "jenkins",
                   "gitlab", "github actions"],
        "cloud": ["aws", "gcp", "azure", "cloud", "serverless", "lambda", "cloud run", "s3"],

        # Data & AI
        "data-science": ["ml", "machine learning", "model", "training", "dataset", "neural network"],
        "data-engineering": ["pipeline", "etl", "airflow", "spark", "kafka", "streaming", "batch"],

        # Business & Process
        "product": ["feature", "user story", "roadmap", "prd", "requirement", "stakeholder"],
        "qa": ["test", "testing", "quality", "bug", "qa", "unit test", "integration test"],
    }

    CODE_PATTERNS = {
        "python": r"(def\s+\w+|class\s+\w+|import\s+\w+|from\s+\w+\s+import|\.py\b)",
        "javascript": r"(function\s+\w+|const\s+\w+|let\s+\w+|var\s+\w+|=>|\.jsx?\b|\.tsx?\b)",
        "sql": r"\b(SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|JOIN|CREATE\s+TABLE)\b",
        "dockerfile": r"\b(FROM|RUN|COPY|CMD|ENTRYPOINT|WORKDIR)\b",
        "yaml": r"(apiVersion|kind:|metadata:|spec:)",
        "json": r'[\{\[][\s\S]*?[\}\]]',
    }

    TASK_KEYWORDS = {
        "review": ["review", "analyze", "check", "audit", "evaluate", "assess"],
        "design": ["design", "architect", "plan", "create schema", "structure"],
        "debug": ["bug", "error", "fix", "debug", "issue", "problem", "broken"],
        "optimize": ["optimize", "improve", "performance", "faster", "speed up", "efficient"],
        "implement": ["implement", "build", "create", "develop", "write", "code"],
        "deploy": ["deploy", "setup", "configure", "install", "provision"],
        "test": ["test", "testing", "unit test", "integration test", "e2e"],
        "security": ["secure", "vulnerability", "pentest", "security audit"],
    }

    async def analyze(self, query: str) -> Dict[str, any]:
        """
        Analyzes the query using HYBRID approach.

        1. Check cache first
        2. Try keyword matching
        3. If confidence < threshold, use LLM fallback
        4. Cache result

        Args:
            query: User's query string

        Returns:
            {
                "primary_domain": "python",
                "secondary_domain": "backend",
                "task_type": "review",
                "confidence": 0.85,
                "has_code": True,
                "complexity": "medium",
                "detected_languages": ["python"],
                "method": "keyword" | "llm" | "cached"
            }
        """
        # 1. Check cache
        cache_key = query[:200]  # Use first 200 chars as key
        if cache_key in self._cache:
            logger.info("Using cached result")
            result = self._cache[cache_key].copy()
            result["method"] = "cached"
            return result

        # 2. Try keyword matching first
        keyword_result = self._analyze_with_keywords(query)

        # 3. Decide if LLM fallback is needed
        if self.use_llm_fallback and keyword_result['confidence'] < self.confidence_threshold:
            logger.info(f"Confidence {keyword_result['confidence']:.2f} < {self.confidence_threshold}, using LLM fallback")
            try:
                llm_result = await self._analyze_with_llm(query)
                llm_result["method"] = "llm"
                result = llm_result
            except Exception as e:
                logger.error(f"LLM fallback failed: {e}, using keyword result")
                keyword_result["method"] = "keyword"
                result = keyword_result
        else:
            logger.info(f"Confidence {keyword_result['confidence']:.2f} >= {self.confidence_threshold}, using keyword result")
            keyword_result["method"] = "keyword"
            result = keyword_result

        # 4. Cache result
        self._cache[cache_key] = result.copy()

        return result

    def _analyze_with_keywords(self, query: str) -> Dict[str, any]:
        """
        Original keyword-based analysis (synchronous).

        Args:
            query: User's query string

        Returns:
            Domain analysis dict
        """
        query_lower = query.lower()

        # 1. Detect domains using keywords
        domain_scores = defaultdict(int)
        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            for keyword in keywords:
                if keyword in query_lower:
                    domain_scores[domain] += 1

        # 2. Detect code patterns (gives higher weight)
        code_detected = {}
        for lang, pattern in self.CODE_PATTERNS.items():
            if re.search(pattern, query, re.IGNORECASE | re.MULTILINE):
                code_detected[lang] = True
                domain_scores[lang] += 3  # Higher weight for actual code presence

        # 3. Detect task type
        task_scores = defaultdict(int)
        for task, keywords in self.TASK_KEYWORDS.items():
            for keyword in keywords:
                if keyword in query_lower:
                    task_scores[task] += 1

        # 4. Calculate complexity
        complexity = self._calculate_complexity(query, domain_scores, task_scores)

        # 5. Select primary and secondary domains
        if not domain_scores:
            return {
                "primary_domain": "general",
                "secondary_domain": None,
                "task_type": "general",
                "confidence": 0.3,
                "has_code": False,
                "complexity": "low",
                "detected_languages": []
            }

        sorted_domains = sorted(domain_scores.items(), key=lambda x: x[1], reverse=True)
        primary_domain = sorted_domains[0][0]
        secondary_domain = sorted_domains[1][0] if len(sorted_domains) > 1 and sorted_domains[1][1] > 0 else None

        sorted_tasks = sorted(task_scores.items(), key=lambda x: x[1], reverse=True)
        task_type = sorted_tasks[0][0] if sorted_tasks else "general"

        # 6. Calculate confidence based on signal strength
        max_score = sorted_domains[0][1]
        confidence = min(max_score / 5.0, 1.0)  # Normalize to 0-1

        result = {
            "primary_domain": primary_domain,
            "secondary_domain": secondary_domain,
            "task_type": task_type,
            "confidence": confidence,
            "has_code": bool(code_detected),
            "complexity": complexity,
            "detected_languages": list(code_detected.keys())
        }

        logger.info(f"Domain analysis result: {result}")
        return result

    def _calculate_complexity(self, query: str, domain_scores: dict, task_scores: dict) -> str:
        """
        Determines complexity: low, medium, high, very_high
        """
        score = 0

        # Query length
        if len(query) > 1000:
            score += 3
        elif len(query) > 500:
            score += 2
        elif len(query) > 200:
            score += 1

        # Multiple domains involved
        if len(domain_scores) > 3:
            score += 2
        elif len(domain_scores) > 1:
            score += 1

        # Multiple tasks
        if len(task_scores) > 2:
            score += 1

        # Complex keywords
        complex_keywords = [
            "architecture", "system", "enterprise", "scalable", "production",
            "orchestrate", "integrate", "microservice", "distributed",
            "high availability", "fault tolerant", "multi-region"
        ]
        for kw in complex_keywords:
            if kw in query.lower():
                score += 1

        # Words like "and", "also", "additionally" suggest multi-part tasks
        multi_part_indicators = [" and ", " also ", " additionally ", " furthermore ", " moreover "]
        for indicator in multi_part_indicators:
            if indicator in query.lower():
                score += 0.5

        if score >= 6:
            return "very_high"
        elif score >= 4:
            return "high"
        elif score >= 2:
            return "medium"
        else:
            return "low"

    async def _analyze_with_llm(self, query: str) -> Dict[str, any]:
        """
        Uses Claude Haiku API for precise domain detection.

        Args:
            query: User's query string

        Returns:
            Domain analysis dict with high confidence

        Raises:
            Exception: If API call fails
        """
        try:
            from anthropic import Anthropic
        except ImportError:
            raise Exception("anthropic package not installed")

        # Use existing SecretsManager infrastructure
        from core.secrets_manager import SecretsManager
        secrets = SecretsManager()
        api_key = secrets.get_anthropic_key()

        if not api_key:
            raise Exception("Anthropic API key not found in Secret Manager or environment. "
                          "Please set ANTHROPIC_API_KEY, CLAUDE_API_KEY, or configure Google Secret Manager.")

        client = Anthropic(api_key=api_key)

        # Construct prompt for domain detection
        prompt = f"""Analyze this user query and identify the technical domain and task type.

User query:
{query}

Respond ONLY with valid JSON (no markdown, no explanations):
{{
  "primary_domain": "one of: python|javascript|java|go|rust|cpp|backend|frontend|database|security|penetration|devops|cloud|data-science|data-engineering|product|qa|general",
  "secondary_domain": "one of the above or null",
  "task_type": "one of: review|design|debug|optimize|implement|deploy|test|security|general",
  "complexity": "one of: low|medium|high|very_high",
  "confidence": 0.0-1.0,
  "has_code": true|false
}}

Focus on the PRIMARY intent of the query. For example:
- "Analyze security vulnerabilities in API" → primary_domain: "security" (not backend)
- "Create machine learning pipeline" → primary_domain: "data-science" (not devops)
- "Review React component" → primary_domain: "frontend" (not javascript)

Confidence should be 0.8-1.0 for clear queries, 0.6-0.8 for ambiguous ones."""

        # Call Haiku (cheaper and faster than Sonnet)
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=300,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        # Parse JSON response
        response_text = response.content[0].text.strip()

        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1])

        result = json.loads(response_text)

        # Add detected_languages (empty for LLM analysis)
        result["detected_languages"] = []

        logger.info(f"LLM analysis: domain={result['primary_domain']}, confidence={result['confidence']}")
        return result

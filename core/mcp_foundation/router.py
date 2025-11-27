"""
MCP Router - AI-Powered intelligent MCP selection

Provides:
- AI-powered MCP selection based on user query
- Load only relevant MCPs for each request
- Reduces context window usage
- Improves response time
"""

import logging
import re
from typing import List, Dict, Optional, Any, Set
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MCPRouting:
    """Result of MCP routing"""
    selected_mcps: List[str]
    confidence: float
    reasoning: str
    categories_used: Set[str]


class MCPRouter:
    """
    AI-Powered MCP Router

    Intelligently selects which MCPs to load based on user query.
    Dramatically reduces:
    - Context window usage
    - Memory usage
    - Response time
    """

    def __init__(self, registry):
        """
        Initialize router

        Args:
            registry: MCPRegistry instance
        """
        self.registry = registry

        # MCP capability keywords for intelligent routing
        self._mcp_keywords = self._build_keyword_map()

    def _build_keyword_map(self) -> Dict[str, Set[str]]:
        """
        Build keyword mapping for MCP routing

        Maps keywords in user queries to relevant MCPs
        """
        return {
            # Google Workspace
            "google-workspace": {
                "email", "gmail", "mail", "send message", "inbox",
                "drive", "file", "document", "doc", "sheet", "spreadsheet",
                "calendar", "schedule", "meeting", "event", "appointment",
                "form", "survey", "task", "todo", "chat", "slide", "presentation",
            },

            # Communication
            "slack": {
                "slack", "channel", "dm", "direct message", "notification",
                "team chat", "workspace message",
            },
            "teams": {
                "microsoft teams", "teams", "teams channel", "teams call",
            },
            "discord": {
                "discord", "discord server", "discord channel", "discord bot",
            },

            # Databases
            "postgresql": {
                "postgres", "postgresql", "sql", "database", "table", "query",
                "select", "insert", "update", "delete", "relational",
            },
            "mongodb": {
                "mongo", "mongodb", "nosql", "document", "collection",
                "find", "aggregate", "json data",
            },
            "redis": {
                "redis", "cache", "key-value", "pub/sub", "subscribe",
                "publish", "expire", "ttl",
            },
            "sqlite": {
                "sqlite", "local database", "embedded database", "local sql",
            },

            # Cloud
            "gcp": {
                "google cloud", "gcp", "gke", "cloud run", "bigquery",
                "cloud storage", "compute engine",
            },
            "kubernetes": {
                "kubernetes", "k8s", "pod", "deployment", "service",
                "kubectl", "cluster", "namespace",
            },
            "aws": {
                "aws", "amazon", "ec2", "s3", "lambda", "dynamodb", "rds",
            },

            # Development
            "github": {
                "github", "git", "repository", "repo", "commit", "pull request",
                "pr", "issue", "branch", "merge",
            },
            "docker": {
                "docker", "container", "image", "dockerfile", "docker-compose",
                "containerize",
            },
            "puppeteer": {
                "puppeteer", "browser", "screenshot", "pdf", "scrape",
                "headless chrome", "automate web",
            },
            "playwright": {
                "playwright", "browser test", "e2e", "end-to-end", "automation",
            },

            # Monitoring
            "sentry": {
                "sentry", "error", "exception", "bug", "stack trace",
                "error tracking", "crash",
            },

            # Project Management
            "jira": {
                "jira", "ticket", "story", "epic", "sprint", "scrum",
                "issue tracker", "atlassian",
            },
            "notion": {
                "notion", "wiki", "note", "documentation", "knowledge base",
                "page", "database notion",
            },

            # Search
            "brave-search": {
                "search", "web search", "google search", "find online",
                "look up", "research", "browse web",
            },

            # CRM
            "hubspot": {
                "hubspot", "crm", "contact", "lead", "deal", "customer",
                "sales pipeline",
            },

            # Payments
            "stripe": {
                "stripe", "payment", "charge", "subscription", "invoice",
                "customer billing", "card",
            },

            # Analytics
            "mixpanel": {
                "mixpanel", "analytics", "event tracking", "user behavior",
                "funnel", "cohort",
            },
        }

    def route(self, query: str, max_mcps: int = 10) -> MCPRouting:
        """
        Route query to relevant MCPs

        Args:
            query: User query
            max_mcps: Maximum number of MCPs to select

        Returns:
            MCPRouting with selected MCPs
        """
        query_lower = query.lower()

        # Score each MCP
        scores: Dict[str, float] = {}
        matched_keywords: Dict[str, Set[str]] = {}

        for mcp_name, keywords in self._mcp_keywords.items():
            score = 0.0
            matches = set()

            for keyword in keywords:
                if keyword in query_lower:
                    # Longer keywords get higher scores
                    score += len(keyword.split())
                    matches.add(keyword)

            if score > 0:
                scores[mcp_name] = score
                matched_keywords[mcp_name] = matches

        # Sort by score and take top N
        sorted_mcps = sorted(
            scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:max_mcps]

        selected_mcps = [mcp for mcp, _ in sorted_mcps]

        # Calculate confidence
        total_score = sum(scores.values())
        top_score = sum(score for _, score in sorted_mcps)
        confidence = (top_score / total_score) if total_score > 0 else 0.0

        # Build reasoning
        reasoning_parts = []
        for mcp in selected_mcps[:3]:  # Top 3 for reasoning
            if mcp in matched_keywords:
                keywords = ", ".join(list(matched_keywords[mcp])[:3])
                reasoning_parts.append(f"{mcp} (matched: {keywords})")

        reasoning = "; ".join(reasoning_parts) if reasoning_parts else "No specific matches"

        # Get categories
        categories = set()
        for mcp_name in selected_mcps:
            instance = self.registry.get(mcp_name, auto_load=False)
            if instance:
                categories.add(instance.config.category.value)

        logger.info(
            f"Routed query to {len(selected_mcps)} MCPs "
            f"(confidence: {confidence:.2f}): {selected_mcps}"
        )

        return MCPRouting(
            selected_mcps=selected_mcps,
            confidence=confidence,
            reasoning=reasoning,
            categories_used=categories,
        )

    def route_with_fallback(
        self,
        query: str,
        min_confidence: float = 0.3,
        fallback_categories: Optional[List[str]] = None,
    ) -> MCPRouting:
        """
        Route with fallback to default MCPs if confidence is low

        Args:
            query: User query
            min_confidence: Minimum confidence threshold
            fallback_categories: Categories to use as fallback

        Returns:
            MCPRouting
        """
        routing = self.route(query)

        if routing.confidence < min_confidence:
            logger.warning(
                f"Low confidence routing ({routing.confidence:.2f}), "
                f"using fallback"
            )

            # Use fallback categories or defaults
            fallback_categories = fallback_categories or [
                "google_workspace",
                "database",
                "reference",
            ]

            fallback_mcps = []
            for cat_str in fallback_categories:
                from .registry import MCPCategory
                try:
                    cat = MCPCategory(cat_str)
                    instances = self.registry.get_by_category(cat)
                    fallback_mcps.extend([inst.config.name for inst in instances if inst.config.enabled])
                except ValueError:
                    continue

            routing.selected_mcps.extend(fallback_mcps)
            routing.selected_mcps = list(set(routing.selected_mcps))[:10]
            routing.reasoning += f" (fallback to {fallback_categories})"

        return routing

    def route_by_intent(self, intent: str) -> List[str]:
        """
        Route based on explicit intent

        Args:
            intent: Intent name (e.g., "email", "database", "search")

        Returns:
            List of relevant MCP names
        """
        intent_mappings = {
            "email": ["google-workspace", "slack"],
            "database": ["postgresql", "mongodb", "redis", "sqlite"],
            "search": ["brave-search"],
            "cloud": ["gcp", "aws", "kubernetes"],
            "development": ["github", "docker", "puppeteer", "playwright"],
            "monitoring": ["sentry"],
            "project-management": ["jira", "notion"],
            "communication": ["slack", "teams", "discord"],
            "crm": ["hubspot"],
            "payments": ["stripe"],
            "analytics": ["mixpanel"],
        }

        mcps = intent_mappings.get(intent, [])
        logger.info(f"Routed intent '{intent}' to MCPs: {mcps}")
        return mcps

    def get_routing_stats(self) -> Dict[str, Any]:
        """
        Get routing statistics

        Returns:
            Stats about MCP usage patterns
        """
        all_mcps = self.registry.get_all_enabled()

        usage_stats = {
            mcp.config.name: {
                "total_calls": mcp.total_calls,
                "success_count": mcp.success_count,
                "error_count": mcp.error_count,
                "avg_response_time": mcp.avg_response_time,
                "last_used": mcp.last_used,
            }
            for mcp in all_mcps
        }

        # Sort by usage
        sorted_by_usage = sorted(
            usage_stats.items(),
            key=lambda x: x[1]["total_calls"],
            reverse=True
        )

        return {
            "most_used": [name for name, _ in sorted_by_usage[:10]],
            "least_used": [name for name, _ in sorted_by_usage[-10:]],
            "usage_details": usage_stats,
        }

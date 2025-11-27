"""
Meta-MCP Orchestrator - MCP Selector Module

Intelligent selection of MCPs based on task requirements.
Similar to PersonaSelector but for external MCP servers.
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from .mcp_registry import MCPRegistry, ExternalMCP

logger = logging.getLogger(__name__)


@dataclass
class MCPSelectionCriteria:
    """Criteria for selecting MCPs"""
    required_capabilities: List[str] = None
    preferred_categories: List[str] = None
    preferred_transports: List[str] = None
    exclude_mcps: List[str] = None
    only_healthy: bool = True
    min_priority: int = 0
    max_results: int = 3


class MCPSelector:
    """
    Intelligent MCP selector using semantic similarity and multi-criteria scoring.
    Similar to PersonaSelector but for external MCPs.
    """

    def __init__(self, registry: MCPRegistry):
        """
        Initialize MCP Selector.

        Args:
            registry: MCPRegistry instance
        """
        self.registry = registry
        logger.info("MCPSelector initialized")

    def select_mcps(
        self,
        task_description: str,
        criteria: Optional[MCPSelectionCriteria] = None
    ) -> List[Tuple[ExternalMCP, float]]:
        """
        Select best MCPs for a given task.

        Args:
            task_description: Description of the task
            criteria: Selection criteria (optional)

        Returns:
            List of (MCP, score) tuples, sorted by score descending
        """
        if criteria is None:
            criteria = MCPSelectionCriteria()

        logger.info(f"Selecting MCPs for task: {task_description[:100]}...")

        # Step 1: Get candidate MCPs
        candidates = self._get_candidates(criteria)

        if not candidates:
            logger.warning("No candidate MCPs found matching criteria")
            return []

        logger.debug(f"Found {len(candidates)} candidate MCPs")

        # Step 2: Score each MCP
        scored_mcps = []
        for mcp in candidates:
            score = self._score_mcp_for_task(mcp, task_description, criteria)
            if score > 0:
                scored_mcps.append((mcp, score))

        # Step 3: Sort by score (descending)
        scored_mcps.sort(key=lambda x: x[1], reverse=True)

        # Step 4: Return top results
        results = scored_mcps[:criteria.max_results]

        logger.info(f"Selected {len(results)} MCPs: {[mcp.name for mcp, _ in results]}")

        return results

    def _get_candidates(self, criteria: MCPSelectionCriteria) -> List[ExternalMCP]:
        """
        Get candidate MCPs based on criteria filters.

        Args:
            criteria: Selection criteria

        Returns:
            List of candidate MCPs
        """
        candidates = list(self.registry.mcps.values())

        # Filter by health status
        if criteria.only_healthy:
            candidates = [mcp for mcp in candidates if mcp.is_healthy()]
            logger.debug(f"After health filter: {len(candidates)} MCPs")

        # Filter by priority
        if criteria.min_priority > 0:
            candidates = [mcp for mcp in candidates if mcp.priority >= criteria.min_priority]
            logger.debug(f"After priority filter: {len(candidates)} MCPs")

        # Filter by excluded MCPs
        if criteria.exclude_mcps:
            candidates = [mcp for mcp in candidates if mcp.name not in criteria.exclude_mcps]
            logger.debug(f"After exclusion filter: {len(candidates)} MCPs")

        # Filter by required capabilities
        if criteria.required_capabilities:
            candidates = [
                mcp for mcp in candidates
                if all(cap in mcp.capabilities for cap in criteria.required_capabilities)
            ]
            logger.debug(f"After capability filter: {len(candidates)} MCPs")

        # Filter by preferred categories (not strict, just prioritize)
        # Don't exclude, just reorder later

        # Filter by preferred transports (not strict)
        # Don't exclude, just reorder later

        return candidates

    def _score_mcp_for_task(
        self,
        mcp: ExternalMCP,
        task_description: str,
        criteria: MCPSelectionCriteria
    ) -> float:
        """
        Calculate a score for how well an MCP matches the task.
        Uses multiple factors:
        - Semantic similarity (if embeddings available)
        - Capability match
        - Category preference
        - Transport preference
        - Priority
        - Health status

        Args:
            mcp: MCP to score
            task_description: Task description
            criteria: Selection criteria

        Returns:
            Score (0-100)
        """
        score = 0.0
        max_score = 100.0

        # 1. Semantic Similarity (40 points max)
        semantic_score = self._calculate_semantic_similarity(mcp, task_description)
        score += semantic_score * 40

        # 2. Capability Match (30 points max)
        capability_score = self._calculate_capability_match(mcp, criteria)
        score += capability_score * 30

        # 3. Category Preference (10 points max)
        category_score = self._calculate_category_preference(mcp, criteria)
        score += category_score * 10

        # 4. Transport Preference (5 points max)
        transport_score = self._calculate_transport_preference(mcp, criteria)
        score += transport_score * 5

        # 5. Priority (10 points max)
        priority_score = mcp.priority / 100.0  # normalize 0-100 to 0-1
        score += priority_score * 10

        # 6. Health bonus (5 points max)
        if mcp.health_status == "healthy":
            score += 5

        # Normalize to 0-100
        score = min(score, max_score)

        logger.debug(f"MCP '{mcp.name}' scored {score:.2f}/100 (semantic: {semantic_score:.2f}, capability: {capability_score:.2f})")

        return score

    def _calculate_semantic_similarity(self, mcp: ExternalMCP, task_description: str) -> float:
        """
        Calculate semantic similarity between MCP and task.

        Args:
            mcp: MCP to evaluate
            task_description: Task description

        Returns:
            Similarity score (0-1)
        """
        if not self.registry.embedding_generator or mcp.embedding is None:
            # Fallback to simple text matching
            searchable_text = mcp.get_searchable_text().lower()
            task_lower = task_description.lower()

            # Count matching words
            task_words = set(task_lower.split())
            mcp_words = set(searchable_text.split())
            common_words = task_words & mcp_words

            if len(task_words) == 0:
                return 0.0

            return len(common_words) / len(task_words)

        try:
            # Generate embedding for task
            task_embedding = self.registry.embedding_generator(task_description)

            if not isinstance(task_embedding, np.ndarray):
                logger.warning(f"Invalid task embedding type: {type(task_embedding)}")
                return 0.0

            # Calculate cosine similarity
            similarity = np.dot(task_embedding, mcp.embedding) / (
                np.linalg.norm(task_embedding) * np.linalg.norm(mcp.embedding)
            )

            # Convert to 0-1 range (cosine similarity is -1 to 1)
            return max(0.0, (similarity + 1) / 2)

        except Exception as e:
            logger.error(f"Error calculating semantic similarity: {e}")
            return 0.0

    def _calculate_capability_match(self, mcp: ExternalMCP, criteria: MCPSelectionCriteria) -> float:
        """
        Calculate how well MCP capabilities match requirements.

        Args:
            mcp: MCP to evaluate
            criteria: Selection criteria

        Returns:
            Match score (0-1)
        """
        if not criteria.required_capabilities:
            return 1.0  # No requirements, full score

        # Check if all required capabilities are present
        matched = sum(1 for cap in criteria.required_capabilities if cap in mcp.capabilities)
        total = len(criteria.required_capabilities)

        return matched / total if total > 0 else 0.0

    def _calculate_category_preference(self, mcp: ExternalMCP, criteria: MCPSelectionCriteria) -> float:
        """
        Calculate category preference score.

        Args:
            mcp: MCP to evaluate
            criteria: Selection criteria

        Returns:
            Preference score (0-1)
        """
        if not criteria.preferred_categories:
            return 0.5  # Neutral score if no preference

        if mcp.category in criteria.preferred_categories:
            return 1.0
        else:
            return 0.0

    def _calculate_transport_preference(self, mcp: ExternalMCP, criteria: MCPSelectionCriteria) -> float:
        """
        Calculate transport preference score.

        Args:
            mcp: MCP to evaluate
            criteria: Selection criteria

        Returns:
            Preference score (0-1)
        """
        if not criteria.preferred_transports:
            return 0.5  # Neutral score if no preference

        if mcp.transport in criteria.preferred_transports:
            return 1.0
        else:
            return 0.0

    def select_by_capabilities(self, capabilities: List[str], max_results: int = 3) -> List[ExternalMCP]:
        """
        Select MCPs by specific capabilities.

        Args:
            capabilities: List of required capabilities
            max_results: Maximum number of MCPs to return

        Returns:
            List of matching MCPs
        """
        criteria = MCPSelectionCriteria(
            required_capabilities=capabilities,
            max_results=max_results
        )

        # For capability-based selection, semantic similarity is less important
        # Just filter and sort by priority
        candidates = self._get_candidates(criteria)
        candidates.sort(key=lambda mcp: mcp.priority, reverse=True)

        return candidates[:max_results]

    def select_by_category(self, category: str, max_results: int = 3) -> List[ExternalMCP]:
        """
        Select MCPs by category.

        Args:
            category: Category name
            max_results: Maximum number of MCPs to return

        Returns:
            List of matching MCPs
        """
        mcps = self.registry.get_mcps_by_category(category)

        # Filter for healthy MCPs
        mcps = [mcp for mcp in mcps if mcp.is_healthy()]

        # Sort by priority
        mcps.sort(key=lambda mcp: mcp.priority, reverse=True)

        return mcps[:max_results]

    def recommend_mcps_for_task(self, task_description: str, max_results: int = 3) -> List[Dict[str, Any]]:
        """
        Recommend MCPs for a task with detailed explanations.

        Args:
            task_description: Task description
            max_results: Maximum number of recommendations

        Returns:
            List of recommendation dictionaries with MCP details and reasons
        """
        criteria = MCPSelectionCriteria(max_results=max_results)
        selected = self.select_mcps(task_description, criteria)

        recommendations = []
        for mcp, score in selected:
            recommendation = {
                'mcp': mcp.to_dict(),
                'score': score,
                'reasons': self._generate_selection_reasons(mcp, task_description),
                'connection_type': mcp.transport,
                'health_status': mcp.health_status
            }
            recommendations.append(recommendation)

        return recommendations

    def _generate_selection_reasons(self, mcp: ExternalMCP, task_description: str) -> List[str]:
        """
        Generate human-readable reasons for why this MCP was selected.

        Args:
            mcp: Selected MCP
            task_description: Task description

        Returns:
            List of reason strings
        """
        reasons = []

        # Add capability reasons
        if mcp.capabilities:
            reasons.append(f"Provides {len(mcp.capabilities)} capabilities: {', '.join(mcp.capabilities[:3])}")

        # Add category reason
        reasons.append(f"Specialized in {mcp.category}")

        # Add priority reason
        if mcp.priority >= 75:
            reasons.append("High priority MCP (recommended)")
        elif mcp.priority >= 50:
            reasons.append("Standard priority MCP")

        # Add health status
        if mcp.health_status == "healthy":
            reasons.append("Currently healthy and available")

        # Add transport info
        reasons.append(f"Uses {mcp.transport} transport for reliable communication")

        return reasons

    def get_statistics(self) -> Dict[str, Any]:
        """Get selection statistics"""
        stats = self.registry.get_stats()

        stats['selector_ready'] = len(self.registry.mcps) > 0
        stats['semantic_search_enabled'] = self.registry.embedding_generator is not None

        return stats

"""
Advanced RAG Techniques
Query expansion, re-ranking, and hybrid search for better retrieval
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import re

from core.vector_database import get_vector_database, VectorSearchResult
from core.embeddings_generator import get_embeddings_generator
from core.llm_integration import get_llm

logger = logging.getLogger(__name__)


@dataclass
class ExpandedQuery:
    """Query expansion result"""
    original: str
    expanded: List[str]
    synonyms: List[str]
    related_terms: List[str]


@dataclass
class RankedResult:
    """Re-ranked search result"""
    content: str
    score: float
    original_score: float
    rerank_score: float
    metadata: Dict[str, Any]
    relevance_factors: Dict[str, float]


class QueryExpander:
    """
    Query expansion using multiple techniques

    Techniques:
    - LLM-based expansion (synonyms, related terms)
    - Keyword extraction
    - Entity recognition
    - Domain-specific expansion
    """

    def __init__(self, use_llm: bool = True):
        """
        Initialize Query Expander

        Args:
            use_llm: Use LLM for intelligent expansion
        """
        self.use_llm = use_llm
        self.llm = get_llm() if use_llm else None

    async def expand_query(
        self,
        query: str,
        max_expansions: int = 3,
        include_synonyms: bool = True
    ) -> ExpandedQuery:
        """
        Expand query with related terms and synonyms

        Args:
            query: Original query
            max_expansions: Maximum number of expanded queries
            include_synonyms: Include synonyms

        Returns:
            ExpandedQuery with expansions
        """
        expanded = [query]
        synonyms = []
        related_terms = []

        # LLM-based expansion
        if self.use_llm and self.llm:
            try:
                expansion_prompt = f"""
Given this search query: "{query}"

Generate:
1. {max_expansions} alternative phrasings that capture the same intent
2. Key synonyms for main concepts
3. Related technical terms

Format:
ALTERNATIVES:
- alternative 1
- alternative 2

SYNONYMS:
- synonym 1
- synonym 2

RELATED:
- term 1
- term 2
"""
                response = await self.llm.generate(expansion_prompt)

                # Parse response
                content = response.content

                # Extract alternatives
                if "ALTERNATIVES:" in content:
                    alt_section = content.split("ALTERNATIVES:")[1].split("SYNONYMS:")[0]
                    alternatives = [
                        line.strip('- ').strip()
                        for line in alt_section.split('\n')
                        if line.strip().startswith('-')
                    ]
                    expanded.extend(alternatives[:max_expansions])

                # Extract synonyms
                if "SYNONYMS:" in content:
                    syn_section = content.split("SYNONYMS:")[1].split("RELATED:")[0] if "RELATED:" in content else content.split("SYNONYMS:")[1]
                    synonyms = [
                        line.strip('- ').strip()
                        for line in syn_section.split('\n')
                        if line.strip().startswith('-')
                    ]

                # Extract related terms
                if "RELATED:" in content:
                    rel_section = content.split("RELATED:")[1]
                    related_terms = [
                        line.strip('- ').strip()
                        for line in rel_section.split('\n')
                        if line.strip().startswith('-')
                    ]

            except Exception as e:
                logger.warning(f"LLM expansion failed: {e}")

        # Rule-based expansion (fallback)
        if len(expanded) == 1:
            expanded.extend(self._rule_based_expansion(query))

        logger.info(f"Expanded query into {len(expanded)} variants with {len(synonyms)} synonyms")

        return ExpandedQuery(
            original=query,
            expanded=expanded[:max_expansions + 1],
            synonyms=synonyms,
            related_terms=related_terms
        )

    def _rule_based_expansion(self, query: str) -> List[str]:
        """Simple rule-based query expansion"""
        expansions = []

        # Add question forms
        if not query.endswith('?'):
            expansions.append(f"How to {query}?")
            expansions.append(f"What is {query}?")

        # Add variations
        words = query.split()
        if len(words) > 1:
            # Reverse order for some terms
            expansions.append(' '.join(words[::-1]))

        return expansions[:2]


class ResultReranker:
    """
    Re-rank search results using multiple signals

    Signals:
    - Semantic similarity (original vector score)
    - LLM-based relevance scoring
    - Keyword matching
    - Recency (if available)
    - Document quality indicators
    """

    def __init__(self, use_llm: bool = True):
        """
        Initialize Result Reranker

        Args:
            use_llm: Use LLM for relevance scoring
        """
        self.use_llm = use_llm
        self.llm = get_llm() if use_llm else None

    async def rerank_results(
        self,
        query: str,
        results: List[VectorSearchResult],
        top_k: int = 10
    ) -> List[RankedResult]:
        """
        Re-rank search results using multiple signals

        Args:
            query: Search query
            results: Initial search results
            top_k: Number of top results to return

        Returns:
            List of re-ranked results
        """
        ranked_results = []

        for result in results:
            # Calculate relevance factors
            factors = {}

            # 1. Original vector similarity
            factors['vector_similarity'] = result.score

            # 2. Keyword matching
            factors['keyword_match'] = self._keyword_match_score(query, result.content)

            # 3. Document length factor (prefer medium-length)
            factors['length_factor'] = self._length_score(result.content)

            # 4. Quality indicators
            factors['quality'] = self._quality_score(result.content)

            # Combine factors (weighted)
            weights = {
                'vector_similarity': 0.5,
                'keyword_match': 0.2,
                'length_factor': 0.15,
                'quality': 0.15
            }

            rerank_score = sum(
                factors[factor] * weight
                for factor, weight in weights.items()
            )

            # Final score
            final_score = (result.score + rerank_score) / 2

            ranked_results.append(RankedResult(
                content=result.content,
                score=final_score,
                original_score=result.score,
                rerank_score=rerank_score,
                metadata=result.metadata,
                relevance_factors=factors
            ))

        # Sort by final score
        ranked_results.sort(key=lambda x: x.score, reverse=True)

        # LLM-based re-ranking for top candidates
        if self.use_llm and self.llm and len(ranked_results) > 0:
            try:
                top_candidates = ranked_results[:min(5, len(ranked_results))]
                llm_ranked = await self._llm_rerank(query, top_candidates)

                # Merge LLM rankings
                remaining = ranked_results[len(top_candidates):]
                ranked_results = llm_ranked + remaining

            except Exception as e:
                logger.warning(f"LLM re-ranking failed: {e}")

        logger.info(f"Re-ranked {len(results)} results, returning top {top_k}")

        return ranked_results[:top_k]

    def _keyword_match_score(self, query: str, content: str) -> float:
        """Calculate keyword matching score"""
        query_words = set(query.lower().split())
        content_words = set(content.lower().split())

        if not query_words:
            return 0.0

        # Exact matches
        exact_matches = query_words & content_words
        score = len(exact_matches) / len(query_words)

        # Partial matches (substring)
        for qword in query_words:
            if len(qword) > 3:  # Only for longer words
                if any(qword in cword for cword in content_words):
                    score += 0.1

        return min(score, 1.0)

    def _length_score(self, content: str) -> float:
        """Score based on content length (prefer medium-length)"""
        length = len(content)

        # Optimal length: 200-1000 characters
        if 200 <= length <= 1000:
            return 1.0
        elif length < 200:
            return length / 200
        else:
            # Penalize very long documents
            return max(0.5, 1000 / length)

    def _quality_score(self, content: str) -> float:
        """Score based on content quality indicators"""
        score = 0.0

        # Has proper structure (sentences, punctuation)
        sentences = content.split('.')
        if len(sentences) >= 2:
            score += 0.3

        # Has capitalization (indicates proper formatting)
        if any(c.isupper() for c in content):
            score += 0.2

        # Has numbers/data (often indicates specific information)
        if any(c.isdigit() for c in content):
            score += 0.2

        # Not too many special characters
        special_chars = sum(1 for c in content if not c.isalnum() and not c.isspace())
        if special_chars / max(len(content), 1) < 0.1:
            score += 0.3

        return min(score, 1.0)

    async def _llm_rerank(
        self,
        query: str,
        candidates: List[RankedResult]
    ) -> List[RankedResult]:
        """Use LLM to re-rank top candidates"""

        # Prepare candidates for LLM
        candidates_text = "\n\n".join([
            f"[{i+1}] {c.content[:300]}..."
            for i, c in enumerate(candidates)
        ])

        rerank_prompt = f"""
Query: "{query}"

Rank these search results by relevance (most relevant first).
Just provide the ranking as numbers separated by spaces.

{candidates_text}

Ranking (e.g., "3 1 4 2 5"):"""

        try:
            response = await self.llm.generate(rerank_prompt)
            content = response.content.strip()

            # Parse ranking
            ranking = []
            numbers = re.findall(r'\d+', content)

            for num_str in numbers:
                num = int(num_str)
                if 1 <= num <= len(candidates):
                    ranking.append(num - 1)  # Convert to 0-indexed

            # Reorder candidates
            if len(ranking) == len(candidates):
                reordered = [candidates[i] for i in ranking]

                # Boost scores based on LLM ranking
                for i, result in enumerate(reordered):
                    boost = (len(reordered) - i) / len(reordered) * 0.2
                    result.score += boost

                return reordered

        except Exception as e:
            logger.error(f"LLM rerank parsing failed: {e}")

        return candidates


class HybridSearchSystem:
    """
    Advanced RAG with query expansion and re-ranking

    Pipeline:
    1. Query expansion (multiple phrasings)
    2. Multiple parallel searches
    3. Result aggregation
    4. Re-ranking with multiple signals
    5. Deduplication
    """

    def __init__(
        self,
        enable_query_expansion: bool = True,
        enable_reranking: bool = True,
        use_llm: bool = True
    ):
        """
        Initialize Hybrid Search System

        Args:
            enable_query_expansion: Enable query expansion
            enable_reranking: Enable result re-ranking
            use_llm: Use LLM for expansion and ranking
        """
        self.enable_query_expansion = enable_query_expansion
        self.enable_reranking = enable_reranking

        self.vector_db = get_vector_database()
        self.embeddings = get_embeddings_generator()

        self.query_expander = QueryExpander(use_llm=use_llm) if enable_query_expansion else None
        self.reranker = ResultReranker(use_llm=use_llm) if enable_reranking else None

        self.enabled = (
            self.vector_db and
            self.vector_db.client is not None and
            self.embeddings is not None
        )

        logger.info(f"Hybrid Search System initialized (enabled: {self.enabled})")

    async def search(
        self,
        query: str,
        limit: int = 10,
        score_threshold: float = 0.7
    ) -> List[RankedResult]:
        """
        Advanced hybrid search

        Args:
            query: Search query
            limit: Maximum results
            score_threshold: Minimum score threshold

        Returns:
            List of ranked results
        """
        if not self.enabled:
            return []

        try:
            all_results = []

            # 1. Query expansion
            if self.enable_query_expansion and self.query_expander:
                logger.info("Step 1: Expanding query...")
                expansion = await self.query_expander.expand_query(query)
                queries = expansion.expanded

                logger.info(f"Expanded into {len(queries)} queries")
            else:
                queries = [query]

            # 2. Parallel searches
            logger.info("Step 2: Performing parallel searches...")
            for q in queries:
                # Generate embedding
                embedding = self.embeddings.generate(q).embedding

                # Search
                results = self.vector_db.search(
                    query_embedding=embedding,
                    limit=limit * 2,  # Get more for aggregation
                    score_threshold=score_threshold
                )

                all_results.extend(results)

            logger.info(f"Retrieved {len(all_results)} total results")

            # 3. Deduplicate
            unique_results = self._deduplicate_results(all_results)
            logger.info(f"Deduplicated to {len(unique_results)} unique results")

            # 4. Re-rank
            if self.enable_reranking and self.reranker:
                logger.info("Step 3: Re-ranking results...")
                ranked = await self.reranker.rerank_results(
                    query=query,
                    results=unique_results,
                    top_k=limit
                )
                return ranked
            else:
                # Convert to RankedResult without re-ranking
                return [
                    RankedResult(
                        content=r.content,
                        score=r.score,
                        original_score=r.score,
                        rerank_score=0.0,
                        metadata=r.metadata,
                        relevance_factors={'vector_similarity': r.score}
                    )
                    for r in unique_results[:limit]
                ]

        except Exception as e:
            logger.error(f"Hybrid search error: {e}")
            return []

    def _deduplicate_results(
        self,
        results: List[VectorSearchResult]
    ) -> List[VectorSearchResult]:
        """
        Deduplicate results based on content similarity

        Args:
            results: List of results

        Returns:
            Deduplicated list
        """
        seen_content = set()
        unique = []

        for result in results:
            # Use first 100 chars as fingerprint
            fingerprint = result.content[:100].lower().strip()

            if fingerprint not in seen_content:
                seen_content.add(fingerprint)
                unique.append(result)

        return unique


# Global hybrid search system
_hybrid_search: Optional[HybridSearchSystem] = None


def get_hybrid_search(
    enable_query_expansion: bool = True,
    enable_reranking: bool = True,
    use_llm: bool = True
) -> HybridSearchSystem:
    """
    Get global hybrid search system

    Args:
        enable_query_expansion: Enable query expansion
        enable_reranking: Enable re-ranking
        use_llm: Use LLM

    Returns:
        HybridSearchSystem instance
    """
    global _hybrid_search

    if _hybrid_search is None:
        _hybrid_search = HybridSearchSystem(
            enable_query_expansion=enable_query_expansion,
            enable_reranking=enable_reranking,
            use_llm=use_llm
        )

    return _hybrid_search


if __name__ == "__main__":
    # Test advanced RAG
    import asyncio
    logging.basicConfig(level=logging.INFO)

    print("\n" + "="*60)
    print("Testing Advanced RAG System")
    print("="*60 + "\n")

    async def test_advanced_rag():
        # Initialize system
        hybrid = get_hybrid_search(
            enable_query_expansion=True,
            enable_reranking=True,
            use_llm=False  # Disable LLM for quick testing
        )

        print(f"System enabled: {hybrid.enabled}\n")

        if not hybrid.enabled:
            print("⚠️  Advanced RAG not available")
            print("Ensure Vector DB and embeddings are configured")
            return

        # Test query
        query = "How to optimize Python code performance?"

        print(f"Query: {query}\n")
        print("-"*60)

        # Search
        results = await hybrid.search(query, limit=5)

        print(f"\nFound {len(results)} results:\n")

        for i, result in enumerate(results, 1):
            print(f"{i}. Score: {result.score:.3f}")
            print(f"   Original: {result.original_score:.3f}")
            print(f"   Rerank: {result.rerank_score:.3f}")
            print(f"   Content: {result.content[:100]}...")
            print(f"   Factors: {result.relevance_factors}")
            print()

    asyncio.run(test_advanced_rag())

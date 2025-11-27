#!/usr/bin/env python3
"""
RAG Auto-Integration - Automatic context retrieval for Trinity Router
Simplified RAG system that works without external dependencies
Integrates with existing intelligent_rag_system when available
"""

import json
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class RAGContext:
    """Context retrieved from RAG system"""
    query: str
    contexts: List[Dict[str, Any]]
    relevance_scores: List[float]
    total_results: int
    retrieval_time_ms: int
    source: str  # "memory", "knowledge", "sessions"


@dataclass
class EnrichedQuery:
    """Query enriched with RAG context"""
    original_query: str
    enriched_query: str
    contexts: List[Dict[str, Any]]
    context_summary: str
    confidence: float


class RAGAutoIntegration:
    """
    RAG Auto-Integration - Automatically retrieves context when needed

    Features:
    - Auto-trigger based on query patterns
    - Simplified in-memory storage (no Qdrant dependency)
    - Integration with existing intelligent_rag_system when available
    - Context enrichment for personas
    """

    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize RAG Auto-Integration

        Args:
            storage_path: Optional path for persistent storage
        """
        self.storage_path = storage_path or ".rag_storage"
        self.memory_store = self._load_memory_store()

        # Try to import existing RAG system
        self.has_intelligent_rag = False
        self.intelligent_rag = None
        try:
            from core.intelligent_rag_system import IntelligentRAGSystem
            # Don't initialize yet (requires Qdrant)
            # self.intelligent_rag = IntelligentRAGSystem()
            self.has_intelligent_rag = True
            logger.info("✅ Intelligent RAG system available (not initialized)")
        except Exception as e:
            logger.info(f"ℹ️  Intelligent RAG not available: {e}")
            logger.info("   Using simplified in-memory RAG")

        self.stats = {
            "total_retrievals": 0,
            "cache_hits": 0,
            "context_enrichments": 0,
            "average_relevance": 0.0
        }

    def _load_memory_store(self) -> Dict[str, List[Dict]]:
        """Load memory store from disk"""
        storage_file = Path(self.storage_path) / "memory_store.json"

        if storage_file.exists():
            try:
                with open(storage_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load memory store: {e}")

        return {
            "conversations": [],
            "solutions": [],
            "knowledge": []
        }

    def _save_memory_store(self):
        """Save memory store to disk"""
        storage_file = Path(self.storage_path) / "memory_store.json"
        storage_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(storage_file, 'w') as f:
                json.dump(self.memory_store, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save memory store: {e}")

    def should_use_rag(self, query: str) -> bool:
        """
        Determine if RAG should be used for this query

        Args:
            query: User query

        Returns:
            True if RAG should be triggered
        """
        query_lower = query.lower()

        # Patterns that indicate need for context
        context_patterns = [
            "continue", "previous", "last time", "before",
            "remember", "recall", "earlier", "yesterday",
            "based on", "from before", "like we discussed",
            "the one we", "that we talked about"
        ]

        # Check for context patterns
        for pattern in context_patterns:
            if pattern in query_lower:
                logger.info(f"   🔍 RAG triggered by pattern: '{pattern}'")
                return True

        # Check query length (longer queries might need context)
        if len(query.split()) > 30:
            logger.info("   🔍 RAG triggered by query length")
            return True

        return False

    async def retrieve_context(
        self,
        query: str,
        limit: int = 5,
        min_relevance: float = 0.5
    ) -> RAGContext:
        """
        Retrieve relevant context for query

        Args:
            query: Search query
            limit: Maximum number of results
            min_relevance: Minimum relevance score

        Returns:
            RAGContext with retrieved information
        """
        start_time = time.time()

        logger.info(f"   📚 Retrieving RAG context for: {query[:50]}...")

        # Try intelligent RAG if available
        if self.has_intelligent_rag and self.intelligent_rag:
            try:
                results = await self._retrieve_intelligent_rag(query, limit)
                retrieval_time_ms = int((time.time() - start_time) * 1000)

                self.stats["total_retrievals"] += 1

                return RAGContext(
                    query=query,
                    contexts=results,
                    relevance_scores=[r.get("score", 0.0) for r in results],
                    total_results=len(results),
                    retrieval_time_ms=retrieval_time_ms,
                    source="intelligent_rag"
                )
            except Exception as e:
                logger.warning(f"   Intelligent RAG failed: {e}, falling back to simple")

        # Fallback: Simple keyword-based search
        results = self._simple_search(query, limit, min_relevance)
        retrieval_time_ms = int((time.time() - start_time) * 1000)

        self.stats["total_retrievals"] += 1

        return RAGContext(
            query=query,
            contexts=results,
            relevance_scores=[r.get("score", 0.0) for r in results],
            total_results=len(results),
            retrieval_time_ms=retrieval_time_ms,
            source="simple_memory"
        )

    async def _retrieve_intelligent_rag(self, query: str, limit: int) -> List[Dict]:
        """Retrieve from intelligent RAG system"""
        # This would integrate with the existing intelligent_rag_system
        # For now, return empty as it requires Qdrant setup
        return []

    def _simple_search(
        self,
        query: str,
        limit: int,
        min_relevance: float
    ) -> List[Dict]:
        """Simple keyword-based search in memory store"""
        query_words = set(query.lower().split())
        results = []

        # Search in conversations
        for conv in self.memory_store.get("conversations", []):
            text = conv.get("text", "").lower()
            text_words = set(text.split())

            # Calculate simple overlap score
            overlap = len(query_words & text_words)
            score = overlap / max(len(query_words), 1)

            if score >= min_relevance:
                results.append({
                    "text": conv.get("text", ""),
                    "score": score,
                    "timestamp": conv.get("timestamp", ""),
                    "type": "conversation"
                })

        # Search in solutions
        for sol in self.memory_store.get("solutions", []):
            problem = sol.get("problem", "").lower()
            solution = sol.get("solution", "").lower()
            combined = f"{problem} {solution}"
            combined_words = set(combined.split())

            overlap = len(query_words & combined_words)
            score = overlap / max(len(query_words), 1)

            if score >= min_relevance:
                results.append({
                    "text": f"Problem: {sol.get('problem', '')}\nSolution: {sol.get('solution', '')}",
                    "score": score,
                    "timestamp": sol.get("timestamp", ""),
                    "type": "solution"
                })

        # Sort by score and limit
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    async def enrich_query(
        self,
        query: str,
        strategy: str = "append"  # "append", "prepend", "replace"
    ) -> EnrichedQuery:
        """
        Enrich query with RAG context

        Args:
            query: Original query
            strategy: How to integrate context

        Returns:
            EnrichedQuery with context added
        """
        logger.info(f"   ✨ Enriching query with RAG context...")

        # Retrieve context
        rag_context = await self.retrieve_context(query)

        if not rag_context.contexts:
            logger.info("   ℹ️  No relevant context found")
            return EnrichedQuery(
                original_query=query,
                enriched_query=query,
                contexts=[],
                context_summary="No relevant context found",
                confidence=0.5
            )

        # Build context summary
        context_summary = self._build_context_summary(rag_context.contexts)

        # Enrich query based on strategy
        if strategy == "append":
            enriched_query = f"{query}\n\nRelevant context:\n{context_summary}"
        elif strategy == "prepend":
            enriched_query = f"Context:\n{context_summary}\n\nQuery: {query}"
        else:  # replace (for very contextual queries)
            enriched_query = f"{context_summary}\n\nBased on the above, {query}"

        # Calculate confidence
        avg_relevance = sum(rag_context.relevance_scores) / len(rag_context.relevance_scores) if rag_context.relevance_scores else 0.0
        confidence = 0.5 + (avg_relevance * 0.5)  # 0.5-1.0 range

        self.stats["context_enrichments"] += 1
        self.stats["average_relevance"] = (
            (self.stats["average_relevance"] * (self.stats["context_enrichments"] - 1) + avg_relevance) /
            self.stats["context_enrichments"]
        )

        logger.info(f"   ✅ Query enriched with {len(rag_context.contexts)} contexts (confidence: {confidence:.2f})")

        return EnrichedQuery(
            original_query=query,
            enriched_query=enriched_query,
            contexts=rag_context.contexts,
            context_summary=context_summary,
            confidence=confidence
        )

    def _build_context_summary(self, contexts: List[Dict]) -> str:
        """Build summary from context documents"""
        summary_parts = []

        for i, ctx in enumerate(contexts[:3], 1):  # Top 3
            text = ctx.get("text", "")
            score = ctx.get("score", 0.0)

            # Truncate long texts
            if len(text) > 200:
                text = text[:200] + "..."

            summary_parts.append(f"{i}. [{ctx.get('type', 'unknown')}] {text} (relevance: {score:.2f})")

        return "\n".join(summary_parts)

    def store_interaction(
        self,
        query: str,
        response: str,
        metadata: Optional[Dict] = None
    ):
        """
        Store interaction for future retrieval

        Args:
            query: User query
            response: System response
            metadata: Optional metadata
        """
        interaction = {
            "query": query,
            "response": response,
            "text": f"Q: {query}\nA: {response}",
            "timestamp": time.time(),
            "metadata": metadata or {}
        }

        self.memory_store["conversations"].append(interaction)

        # Keep last 100 conversations
        if len(self.memory_store["conversations"]) > 100:
            self.memory_store["conversations"] = self.memory_store["conversations"][-100:]

        # Save periodically
        if len(self.memory_store["conversations"]) % 10 == 0:
            self._save_memory_store()

    def store_solution(
        self,
        problem: str,
        solution: str,
        tags: Optional[List[str]] = None
    ):
        """Store problem-solution pair"""
        solution_entry = {
            "problem": problem,
            "solution": solution,
            "timestamp": time.time(),
            "tags": tags or []
        }

        self.memory_store["solutions"].append(solution_entry)

        # Keep last 50 solutions
        if len(self.memory_store["solutions"]) > 50:
            self.memory_store["solutions"] = self.memory_store["solutions"][-50:]

        self._save_memory_store()

    def get_stats(self) -> Dict[str, Any]:
        """Get RAG statistics"""
        return {
            **self.stats,
            "stored_conversations": len(self.memory_store.get("conversations", [])),
            "stored_solutions": len(self.memory_store.get("solutions", [])),
            "has_intelligent_rag": self.has_intelligent_rag
        }


# Convenience functions
async def retrieve_context(query: str, limit: int = 5) -> RAGContext:
    """Retrieve context (convenience function)"""
    rag = RAGAutoIntegration()
    return await rag.retrieve_context(query, limit)


async def enrich_query(query: str) -> EnrichedQuery:
    """Enrich query with context (convenience function)"""
    rag = RAGAutoIntegration()
    return await rag.enrich_query(query)


if __name__ == "__main__":
    # Test RAG Auto-Integration
    import asyncio

    async def test_rag():
        print("=" * 80)
        print("RAG AUTO-INTEGRATION TEST")
        print("=" * 80)

        rag = RAGAutoIntegration()

        # Test 1: Store some interactions
        print("\n1. Storing test interactions...")
        rag.store_interaction(
            "How do I deploy to Kubernetes?",
            "Use kubectl apply -f deployment.yaml...",
            {"domain": "devops"}
        )
        rag.store_interaction(
            "What's the best way to scale microservices?",
            "Use horizontal pod autoscaling with metrics...",
            {"domain": "architecture"}
        )
        rag.store_solution(
            "Database connection pooling",
            "Use connection pool with max_connections=10",
            tags=["database", "performance"]
        )

        print(f"   Stored: {len(rag.memory_store['conversations'])} conversations")
        print(f"   Stored: {len(rag.memory_store['solutions'])} solutions")

        # Test 2: Check if RAG should be used
        print("\n2. Testing RAG trigger detection...")
        queries = [
            "Fix this bug",
            "Continue from where we left off yesterday",
            "Based on our previous discussion about Kubernetes"
        ]

        for query in queries:
            should_use = rag.should_use_rag(query)
            print(f"   '{query[:40]}...' → RAG: {should_use}")

        # Test 3: Retrieve context
        print("\n3. Testing context retrieval...")
        context = await rag.retrieve_context("How to deploy microservices?", limit=3)
        print(f"   Query: {context.query}")
        print(f"   Results: {context.total_results}")
        print(f"   Time: {context.retrieval_time_ms}ms")
        print(f"   Source: {context.source}")

        if context.contexts:
            print(f"   Top result: {context.contexts[0].get('text', '')[:80]}...")

        # Test 4: Enrich query
        print("\n4. Testing query enrichment...")
        enriched = await rag.enrich_query("Continue with the Kubernetes deployment")
        print(f"   Original: {enriched.original_query}")
        print(f"   Enriched: {enriched.enriched_query[:100]}...")
        print(f"   Contexts: {len(enriched.contexts)}")
        print(f"   Confidence: {enriched.confidence:.2f}")

        # Test 5: Statistics
        print("\n5. RAG Statistics:")
        stats = rag.get_stats()
        for key, value in stats.items():
            print(f"   {key}: {value}")

    # Run test
    asyncio.run(test_rag())

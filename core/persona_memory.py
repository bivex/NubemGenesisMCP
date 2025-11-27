"""
Persona Memory - Long-term memory for personas using vector database
Each persona has persistent memory of conversations and learnings
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import hashlib

from core.vector_database import get_vector_database, VectorSearchResult
from core.embeddings_generator import get_embeddings_generator

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """Entry in persona memory"""
    persona_key: str
    content: str
    timestamp: datetime
    memory_type: str  # 'conversation', 'learning', 'decision', 'insight'
    context: Optional[Dict[str, Any]] = None
    importance: float = 0.5  # 0-1, higher = more important
    embedding_id: Optional[str] = None


@dataclass
class MemorySearchResult:
    """Result from memory search"""
    entry: MemoryEntry
    score: float
    relevance: str  # 'high', 'medium', 'low'


class PersonaMemory:
    """
    Long-term memory system for personas using vector database

    Features:
    - Store conversation history and learnings
    - Semantic search for relevant memories
    - Memory importance scoring
    - Automatic memory summarization
    - Cross-persona memory sharing (optional)
    """

    def __init__(
        self,
        persona_key: str,
        collection_suffix: str = "_memory",
        max_memory_size: int = 10000,
        embeddings_model: str = 'base'
    ):
        """
        Initialize Persona Memory

        Args:
            persona_key: Key of the persona
            collection_suffix: Suffix for memory collection
            max_memory_size: Maximum number of memories to store
            embeddings_model: Model to use for embeddings
        """
        self.persona_key = persona_key
        self.collection_name = f"{persona_key}{collection_suffix}"
        self.max_memory_size = max_memory_size

        # Initialize vector database
        self.vector_db = get_vector_database()
        if not self.vector_db or not self.vector_db.client:
            logger.warning(f"Vector database not available for {persona_key}")
            self.enabled = False
        else:
            self.enabled = True

        # Initialize embeddings generator
        try:
            self.embeddings = get_embeddings_generator(model_name=embeddings_model)
            if not self.embeddings:
                logger.warning(f"Embeddings generator not available for {persona_key}")
                self.enabled = False
        except Exception as e:
            logger.warning(f"Failed to initialize embeddings: {e}")
            self.enabled = False

        # In-memory cache (most recent memories)
        self.memory_cache: List[MemoryEntry] = []
        self.cache_size = 100

    def add_memory(
        self,
        content: str,
        memory_type: str = 'conversation',
        context: Optional[Dict[str, Any]] = None,
        importance: float = 0.5
    ) -> bool:
        """
        Add a memory to persona's long-term storage

        Args:
            content: Memory content
            memory_type: Type of memory
            context: Additional context
            importance: Importance score (0-1)

        Returns:
            True if memory was added successfully
        """
        if not self.enabled:
            logger.debug(f"Memory system disabled for {self.persona_key}")
            return False

        try:
            # Create memory entry
            entry = MemoryEntry(
                persona_key=self.persona_key,
                content=content,
                timestamp=datetime.now(),
                memory_type=memory_type,
                context=context or {},
                importance=importance
            )

            # Generate embedding
            embedding_result = self.embeddings.generate(content)
            embedding = embedding_result.embedding

            # Create unique ID
            entry_id = hashlib.md5(
                f"{self.persona_key}_{content}_{entry.timestamp.isoformat()}".encode()
            ).hexdigest()
            entry.embedding_id = entry_id

            # Store in vector database
            metadata = {
                'persona_key': self.persona_key,
                'memory_type': memory_type,
                'timestamp': entry.timestamp.isoformat(),
                'importance': importance,
                'context': str(context) if context else ''
            }

            success = self.vector_db.add_documents(
                documents=[content],
                embeddings=[embedding],
                metadata=[metadata]
            )

            if success:
                # Add to cache
                self.memory_cache.append(entry)
                if len(self.memory_cache) > self.cache_size:
                    self.memory_cache.pop(0)

                logger.info(f"Added memory for {self.persona_key}: {content[:50]}...")
                return True
            else:
                logger.error(f"Failed to store memory for {self.persona_key}")
                return False

        except Exception as e:
            logger.error(f"Error adding memory: {e}")
            return False

    def search_memories(
        self,
        query: str,
        limit: int = 5,
        memory_type: Optional[str] = None,
        min_importance: float = 0.0,
        score_threshold: float = 0.7
    ) -> List[MemorySearchResult]:
        """
        Search for relevant memories

        Args:
            query: Search query
            limit: Maximum number of results
            memory_type: Filter by memory type
            min_importance: Minimum importance score
            score_threshold: Minimum similarity score

        Returns:
            List of relevant memory search results
        """
        if not self.enabled:
            return []

        try:
            # Generate query embedding
            query_embedding = self.embeddings.generate(query).embedding

            # Search vector database
            results = self.vector_db.search(
                query_embedding=query_embedding,
                limit=limit * 2,  # Get extra for filtering
                score_threshold=score_threshold
            )

            # Filter and convert to MemorySearchResult
            memory_results = []
            for result in results:
                # Filter by persona
                if result.metadata.get('persona_key') != self.persona_key:
                    continue

                # Filter by memory type
                if memory_type and result.metadata.get('memory_type') != memory_type:
                    continue

                # Filter by importance
                importance = float(result.metadata.get('importance', 0.5))
                if importance < min_importance:
                    continue

                # Create memory entry
                entry = MemoryEntry(
                    persona_key=self.persona_key,
                    content=result.content,
                    timestamp=datetime.fromisoformat(result.metadata.get('timestamp', datetime.now().isoformat())),
                    memory_type=result.metadata.get('memory_type', 'conversation'),
                    importance=importance,
                    embedding_id=result.id
                )

                # Determine relevance
                if result.score >= 0.9:
                    relevance = 'high'
                elif result.score >= 0.8:
                    relevance = 'medium'
                else:
                    relevance = 'low'

                memory_results.append(MemorySearchResult(
                    entry=entry,
                    score=result.score,
                    relevance=relevance
                ))

                if len(memory_results) >= limit:
                    break

            logger.info(f"Found {len(memory_results)} relevant memories for {self.persona_key}")
            return memory_results

        except Exception as e:
            logger.error(f"Error searching memories: {e}")
            return []

    def get_recent_memories(
        self,
        limit: int = 10,
        memory_type: Optional[str] = None
    ) -> List[MemoryEntry]:
        """
        Get most recent memories from cache

        Args:
            limit: Number of memories to retrieve
            memory_type: Filter by memory type

        Returns:
            List of recent memory entries
        """
        memories = self.memory_cache

        # Filter by type if specified
        if memory_type:
            memories = [m for m in memories if m.memory_type == memory_type]

        # Return most recent
        return sorted(memories, key=lambda m: m.timestamp, reverse=True)[:limit]

    def summarize_memories(
        self,
        query: Optional[str] = None,
        limit: int = 20
    ) -> str:
        """
        Generate a summary of relevant memories

        Args:
            query: Optional query to focus summary
            limit: Number of memories to include

        Returns:
            Summary text
        """
        if query:
            results = self.search_memories(query, limit=limit)
            memories = [r.entry for r in results]
        else:
            memories = self.get_recent_memories(limit=limit)

        if not memories:
            return "No memories found."

        # Group by type
        by_type: Dict[str, List[MemoryEntry]] = {}
        for memory in memories:
            if memory.memory_type not in by_type:
                by_type[memory.memory_type] = []
            by_type[memory.memory_type].append(memory)

        # Build summary
        summary_parts = [f"Memory Summary for {self.persona_key}:"]

        for memory_type, entries in by_type.items():
            summary_parts.append(f"\n{memory_type.title()} ({len(entries)} entries):")
            for entry in entries[:5]:  # Top 5 per type
                timestamp = entry.timestamp.strftime("%Y-%m-%d %H:%M")
                importance = "⭐" * int(entry.importance * 5)
                summary_parts.append(f"  [{timestamp}] {importance} {entry.content[:100]}...")

        return "\n".join(summary_parts)

    def clear_memories(self, memory_type: Optional[str] = None) -> bool:
        """
        Clear memories (use with caution!)

        Args:
            memory_type: Only clear specific type, or all if None

        Returns:
            True if successful
        """
        # Clear cache
        if memory_type:
            self.memory_cache = [m for m in self.memory_cache if m.memory_type != memory_type]
        else:
            self.memory_cache = []

        # Note: Vector DB collection deletion would be done separately
        logger.warning(f"Cleared {memory_type or 'all'} memories for {self.persona_key}")
        return True

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        return {
            'persona_key': self.persona_key,
            'enabled': self.enabled,
            'cache_size': len(self.memory_cache),
            'max_cache_size': self.cache_size,
            'vector_db_available': self.vector_db and self.vector_db.client is not None,
            'embeddings_available': self.embeddings is not None
        }


# Global memory manager
_memory_managers: Dict[str, PersonaMemory] = {}


def get_persona_memory(persona_key: str) -> PersonaMemory:
    """
    Get or create memory manager for a persona (singleton per persona)

    Args:
        persona_key: Persona key

    Returns:
        PersonaMemory instance
    """
    global _memory_managers

    if persona_key not in _memory_managers:
        _memory_managers[persona_key] = PersonaMemory(persona_key)

    return _memory_managers[persona_key]


if __name__ == "__main__":
    # Test persona memory
    logging.basicConfig(level=logging.INFO)

    print("\n" + "="*60)
    print("Testing Persona Memory")
    print("="*60 + "\n")

    # Create memory for a test persona
    persona_key = "product-manager"
    memory = get_persona_memory(persona_key)

    stats = memory.get_memory_stats()
    print(f"Memory system for {persona_key}:")
    print(f"  Enabled: {stats['enabled']}")
    print(f"  Vector DB: {stats['vector_db_available']}")
    print(f"  Embeddings: {stats['embeddings_available']}")

    if memory.enabled:
        print("\n" + "-"*60)
        print("Adding Test Memories")
        print("-"*60 + "\n")

        # Add test memories
        test_memories = [
            ("Discussed feature prioritization using RICE framework", "learning", 0.8),
            ("User requested roadmap for Q1 2025", "conversation", 0.6),
            ("Identified key metric: user retention rate", "insight", 0.9),
            ("Decided to focus on mobile app improvements", "decision", 0.7),
        ]

        for content, mem_type, importance in test_memories:
            success = memory.add_memory(content, memory_type=mem_type, importance=importance)
            print(f"{'✓' if success else '✗'} Added: {content[:50]}...")

        # Search memories
        print("\n" + "-"*60)
        print("Searching Memories")
        print("-"*60 + "\n")

        query = "How do we prioritize features?"
        results = memory.search_memories(query, limit=3)

        print(f"Query: {query}")
        print(f"Found {len(results)} results:\n")

        for i, result in enumerate(results, 1):
            print(f"{i}. [{result.relevance}] Score: {result.score:.3f}")
            print(f"   {result.entry.content}")
            print(f"   Type: {result.entry.memory_type}, Importance: {result.entry.importance}")
            print()

        # Get summary
        print("\n" + "-"*60)
        print("Memory Summary")
        print("-"*60 + "\n")

        summary = memory.summarize_memories(limit=10)
        print(summary)
    else:
        print("\n⚠️  Memory system not available")
        print("Ensure Vector DB (Qdrant) and embeddings are configured")

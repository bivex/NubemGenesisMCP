"""
Cross-Persona Shared Memory System
Allows personas to share knowledge, insights, and learnings across the system
"""

import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from core.vector_database import get_vector_database
from core.embeddings_generator import get_embeddings_generator
from core.persona_memory import PersonaMemory, MemoryEntry, MemorySearchResult

logger = logging.getLogger(__name__)


class SharingScope(Enum):
    """Scope of memory sharing"""
    PRIVATE = "private"  # Only this persona
    TEAM = "team"  # Shared with specific team
    PUBLIC = "public"  # Shared with all personas
    HIERARCHICAL = "hierarchical"  # Shared up the hierarchy


class MemoryAccessLevel(Enum):
    """Access level for shared memories"""
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    CONTRIBUTE = "contribute"  # Can add but not modify


@dataclass
class SharedMemoryEntry(MemoryEntry):
    """Extended memory entry with sharing metadata"""
    sharing_scope: SharingScope = SharingScope.PRIVATE
    shared_with: Set[str] = field(default_factory=set)  # Persona keys
    shared_by: Optional[str] = None  # Original contributor
    access_level: MemoryAccessLevel = MemoryAccessLevel.READ_ONLY
    tags: List[str] = field(default_factory=list)
    upvotes: int = 0
    usage_count: int = 0


@dataclass
class MemorySharingRule:
    """Rules for automatic memory sharing"""
    source_persona: str
    target_personas: List[str]
    memory_types: List[str]  # Which types to share
    min_importance: float  # Minimum importance to share
    auto_share: bool = True


class SharedMemorySystem:
    """
    Cross-persona memory sharing system

    Features:
    - Share memories between personas
    - Team-based memory pools
    - Hierarchical knowledge sharing
    - Access control and permissions
    - Automatic sharing rules
    - Memory upvoting and usage tracking
    """

    def __init__(
        self,
        collection_name: str = "shared_memories",
        enable_auto_sharing: bool = True
    ):
        """
        Initialize Shared Memory System

        Args:
            collection_name: Name of shared memory collection
            enable_auto_sharing: Enable automatic sharing based on rules
        """
        self.collection_name = collection_name
        self.enable_auto_sharing = enable_auto_sharing

        # Initialize components
        self.vector_db = get_vector_database()
        self.embeddings = get_embeddings_generator()

        # Check availability
        self.enabled = (
            self.vector_db and
            self.vector_db.client is not None and
            self.embeddings is not None
        )

        # Sharing rules and teams
        self.sharing_rules: Dict[str, List[MemorySharingRule]] = {}
        self.teams: Dict[str, Set[str]] = {}  # team_name -> set of persona_keys

        # Hierarchies (for hierarchical sharing)
        self.hierarchies: Dict[str, List[str]] = {}  # persona_key -> [managers]

        logger.info(f"Shared Memory System initialized (enabled: {self.enabled})")

    def create_team(self, team_name: str, members: List[str]):
        """
        Create a team for memory sharing

        Args:
            team_name: Name of the team
            members: List of persona keys
        """
        self.teams[team_name] = set(members)
        logger.info(f"Created team '{team_name}' with {len(members)} members")

    def add_to_team(self, team_name: str, persona_key: str):
        """Add persona to team"""
        if team_name not in self.teams:
            self.teams[team_name] = set()
        self.teams[team_name].add(persona_key)
        logger.info(f"Added {persona_key} to team '{team_name}'")

    def set_hierarchy(self, persona_key: str, managers: List[str]):
        """
        Set hierarchical relationships

        Args:
            persona_key: Persona key
            managers: List of manager persona keys (in order)
        """
        self.hierarchies[persona_key] = managers
        logger.info(f"Set hierarchy for {persona_key}: {managers}")

    def add_sharing_rule(self, rule: MemorySharingRule):
        """
        Add automatic sharing rule

        Args:
            rule: Memory sharing rule
        """
        if rule.source_persona not in self.sharing_rules:
            self.sharing_rules[rule.source_persona] = []
        self.sharing_rules[rule.source_persona].append(rule)
        logger.info(f"Added sharing rule: {rule.source_persona} -> {rule.target_personas}")

    def share_memory(
        self,
        entry: MemoryEntry,
        sharing_scope: SharingScope,
        shared_with: Optional[List[str]] = None,
        access_level: MemoryAccessLevel = MemoryAccessLevel.READ_ONLY,
        tags: Optional[List[str]] = None
    ) -> bool:
        """
        Share a memory with other personas

        Args:
            entry: Memory entry to share
            sharing_scope: Scope of sharing
            shared_with: Specific personas to share with (for TEAM/PRIVATE)
            access_level: Access level for shared memory
            tags: Tags for categorization

        Returns:
            True if successfully shared
        """
        if not self.enabled:
            return False

        try:
            # Create shared memory entry
            shared_entry = SharedMemoryEntry(
                persona_key=entry.persona_key,
                content=entry.content,
                timestamp=entry.timestamp,
                memory_type=entry.memory_type,
                context=entry.context,
                importance=entry.importance,
                embedding_id=entry.embedding_id,
                sharing_scope=sharing_scope,
                shared_with=set(shared_with) if shared_with else set(),
                shared_by=entry.persona_key,
                access_level=access_level,
                tags=tags or []
            )

            # Generate embedding
            embedding = self.embeddings.generate(entry.content).embedding

            # Prepare metadata
            metadata = {
                'original_persona': entry.persona_key,
                'shared_by': entry.persona_key,
                'memory_type': entry.memory_type,
                'sharing_scope': sharing_scope.value,
                'shared_with': ','.join(shared_entry.shared_with),
                'access_level': access_level.value,
                'tags': ','.join(tags or []),
                'importance': entry.importance,
                'timestamp': entry.timestamp.isoformat(),
                'upvotes': 0,
                'usage_count': 0
            }

            # Store in shared collection
            success = self.vector_db.add_documents(
                documents=[entry.content],
                embeddings=[embedding],
                metadata=[metadata]
            )

            if success:
                logger.info(f"Shared memory from {entry.persona_key} with scope {sharing_scope.value}")
                return True
            else:
                logger.error("Failed to store shared memory")
                return False

        except Exception as e:
            logger.error(f"Error sharing memory: {e}")
            return False

    def search_shared_memories(
        self,
        query: str,
        requesting_persona: str,
        limit: int = 10,
        memory_types: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        min_importance: float = 0.0,
        score_threshold: float = 0.7
    ) -> List[MemorySearchResult]:
        """
        Search shared memories accessible to a persona

        Args:
            query: Search query
            requesting_persona: Persona requesting memories
            limit: Maximum results
            memory_types: Filter by memory types
            tags: Filter by tags
            min_importance: Minimum importance
            score_threshold: Minimum similarity score

        Returns:
            List of accessible shared memories
        """
        if not self.enabled:
            return []

        try:
            # Generate query embedding
            query_embedding = self.embeddings.generate(query).embedding

            # Search shared memories
            results = self.vector_db.search(
                query_embedding=query_embedding,
                limit=limit * 3,  # Get extra for filtering
                score_threshold=score_threshold
            )

            # Filter by access rights
            accessible_results = []

            for result in results:
                # Check if persona has access
                if not self._has_access(requesting_persona, result.metadata):
                    continue

                # Filter by memory type
                if memory_types and result.metadata.get('memory_type') not in memory_types:
                    continue

                # Filter by tags
                if tags:
                    result_tags = result.metadata.get('tags', '').split(',')
                    if not any(tag in result_tags for tag in tags):
                        continue

                # Filter by importance
                importance = float(result.metadata.get('importance', 0.0))
                if importance < min_importance:
                    continue

                # Create memory entry
                entry = MemoryEntry(
                    persona_key=result.metadata.get('original_persona', 'unknown'),
                    content=result.content,
                    timestamp=datetime.fromisoformat(
                        result.metadata.get('timestamp', datetime.now().isoformat())
                    ),
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

                accessible_results.append(MemorySearchResult(
                    entry=entry,
                    score=result.score,
                    relevance=relevance
                ))

                if len(accessible_results) >= limit:
                    break

            # Update usage count (would need separate tracking)
            logger.info(f"Found {len(accessible_results)} shared memories for {requesting_persona}")

            return accessible_results

        except Exception as e:
            logger.error(f"Error searching shared memories: {e}")
            return []

    def _has_access(self, persona_key: str, metadata: Dict[str, Any]) -> bool:
        """
        Check if persona has access to shared memory

        Args:
            persona_key: Requesting persona
            metadata: Memory metadata

        Returns:
            True if has access
        """
        scope = metadata.get('sharing_scope', 'private')

        # Public memories are accessible to all
        if scope == SharingScope.PUBLIC.value:
            return True

        # Private memories only to owner
        if scope == SharingScope.PRIVATE.value:
            return persona_key == metadata.get('original_persona')

        # Team memories
        if scope == SharingScope.TEAM.value:
            shared_with = set(metadata.get('shared_with', '').split(','))
            return persona_key in shared_with

        # Hierarchical memories
        if scope == SharingScope.HIERARCHICAL.value:
            # Check if persona is in the hierarchy
            managers = self.hierarchies.get(metadata.get('original_persona'), [])
            return persona_key in managers

        return False

    def upvote_memory(self, embedding_id: str, persona_key: str) -> bool:
        """
        Upvote a shared memory (increases visibility)

        Args:
            embedding_id: Memory ID
            persona_key: Persona upvoting

        Returns:
            True if successful
        """
        # This would need to update the metadata in vector DB
        # For now, log the action
        logger.info(f"Memory {embedding_id} upvoted by {persona_key}")
        return True

    def auto_share_memory(self, entry: MemoryEntry) -> bool:
        """
        Automatically share memory based on rules

        Args:
            entry: Memory entry

        Returns:
            True if shared
        """
        if not self.enable_auto_sharing:
            return False

        # Get sharing rules for this persona
        rules = self.sharing_rules.get(entry.persona_key, [])

        for rule in rules:
            # Check if memory matches rule criteria
            if entry.memory_type not in rule.memory_types:
                continue

            if entry.importance < rule.min_importance:
                continue

            # Share with target personas
            success = self.share_memory(
                entry=entry,
                sharing_scope=SharingScope.TEAM,
                shared_with=rule.target_personas,
                access_level=MemoryAccessLevel.READ_ONLY,
                tags=[f"auto_shared_from_{entry.persona_key}"]
            )

            if success:
                logger.info(f"Auto-shared memory from {entry.persona_key} to {rule.target_personas}")
                return True

        return False

    def get_team_knowledge_summary(
        self,
        team_name: str,
        limit: int = 50
    ) -> str:
        """
        Get summary of team's shared knowledge

        Args:
            team_name: Team name
            limit: Maximum memories to include

        Returns:
            Summary text
        """
        if team_name not in self.teams:
            return f"Team '{team_name}' not found"

        members = list(self.teams[team_name])

        # Search for all shared memories accessible to team
        all_memories = []
        for member in members[:3]:  # Sample a few members
            memories = self.search_shared_memories(
                query="",  # Empty query gets recent/important
                requesting_persona=member,
                limit=limit
            )
            all_memories.extend(memories)

        if not all_memories:
            return f"No shared knowledge for team '{team_name}'"

        # Build summary
        summary_parts = [f"Shared Knowledge Summary for Team '{team_name}':"]
        summary_parts.append(f"Team Members: {', '.join(members)}")
        summary_parts.append(f"Total Shared Memories: {len(all_memories)}\n")

        # Group by type
        by_type: Dict[str, List[MemorySearchResult]] = {}
        for memory in all_memories[:limit]:
            mem_type = memory.entry.memory_type
            if mem_type not in by_type:
                by_type[mem_type] = []
            by_type[mem_type].append(memory)

        for mem_type, memories in by_type.items():
            summary_parts.append(f"\n{mem_type.title()} ({len(memories)} entries):")
            for memory in memories[:5]:  # Top 5 per type
                summary_parts.append(
                    f"  - [{memory.entry.persona_key}] {memory.entry.content[:100]}..."
                )

        return "\n".join(summary_parts)

    def get_statistics(self) -> Dict[str, Any]:
        """Get shared memory system statistics"""
        return {
            'enabled': self.enabled,
            'teams': {name: len(members) for name, members in self.teams.items()},
            'total_teams': len(self.teams),
            'sharing_rules': sum(len(rules) for rules in self.sharing_rules.values()),
            'hierarchies_defined': len(self.hierarchies),
            'auto_sharing_enabled': self.enable_auto_sharing
        }


# Global shared memory system
_shared_memory: Optional[SharedMemorySystem] = None


def get_shared_memory() -> SharedMemorySystem:
    """
    Get global shared memory system (singleton)

    Returns:
        SharedMemorySystem instance
    """
    global _shared_memory

    if _shared_memory is None:
        _shared_memory = SharedMemorySystem()

    return _shared_memory


# Convenience functions

def create_development_team():
    """Create a default development team with sharing rules"""
    shared_mem = get_shared_memory()

    # Create team
    dev_team = [
        'senior-developer',
        'code-reviewer',
        'security-expert',
        'performance-optimizer',
        'devops-engineer'
    ]

    shared_mem.create_team('development', dev_team)

    # Add sharing rules
    for member in dev_team:
        rule = MemorySharingRule(
            source_persona=member,
            target_personas=[p for p in dev_team if p != member],
            memory_types=['learning', 'insight', 'decision'],
            min_importance=0.7,
            auto_share=True
        )
        shared_mem.add_sharing_rule(rule)

    logger.info("Created development team with auto-sharing rules")


def create_product_team():
    """Create a default product team with sharing rules"""
    shared_mem = get_shared_memory()

    # Create team
    product_team = [
        'product-manager',
        'ux-designer',
        'data-analyst',
        'marketing-strategist'
    ]

    shared_mem.create_team('product', product_team)

    # Add sharing rules
    for member in product_team:
        rule = MemorySharingRule(
            source_persona=member,
            target_personas=[p for p in product_team if p != member],
            memory_types=['insight', 'decision', 'learning'],
            min_importance=0.6,
            auto_share=True
        )
        shared_mem.add_sharing_rule(rule)

    logger.info("Created product team with auto-sharing rules")


if __name__ == "__main__":
    # Test shared memory system
    logging.basicConfig(level=logging.INFO)

    print("\n" + "="*60)
    print("Testing Cross-Persona Shared Memory System")
    print("="*60 + "\n")

    # Initialize system
    shared_mem = get_shared_memory()

    print(f"Shared Memory System:")
    print(f"  Enabled: {shared_mem.enabled}")

    if shared_mem.enabled:
        # Create teams
        create_development_team()
        create_product_team()

        # Get statistics
        stats = shared_mem.get_statistics()
        print(f"\nStatistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")

        # Test memory sharing
        print("\n" + "-"*60)
        print("Testing Memory Sharing")
        print("-"*60 + "\n")

        from core.persona_memory import MemoryEntry

        # Create test memory
        test_memory = MemoryEntry(
            persona_key='senior-developer',
            content='Always use type hints in Python for better code quality',
            timestamp=datetime.now(),
            memory_type='learning',
            importance=0.9
        )

        # Share with team
        success = shared_mem.share_memory(
            entry=test_memory,
            sharing_scope=SharingScope.TEAM,
            shared_with=['code-reviewer', 'junior-developer'],
            tags=['python', 'best-practice']
        )

        print(f"{'✓' if success else '✗'} Shared memory with team")

        # Search shared memories
        print("\n" + "-"*60)
        print("Searching Shared Memories")
        print("-"*60 + "\n")

        results = shared_mem.search_shared_memories(
            query="Python best practices",
            requesting_persona='code-reviewer',
            limit=5
        )

        print(f"Found {len(results)} accessible memories")
        for i, result in enumerate(results, 1):
            print(f"{i}. [{result.relevance}] Score: {result.score:.3f}")
            print(f"   From: {result.entry.persona_key}")
            print(f"   {result.entry.content[:80]}...")
            print()
    else:
        print("\n⚠️  Shared Memory System not available")
        print("Ensure Vector DB and embeddings are configured")

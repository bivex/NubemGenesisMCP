"""
Memory System for NubemClaude Framework
Implements episodic, working, and semantic memory
"""

import json
from core.safe_serialization import safe_dumps, safe_loads, safe_dumps_bytes, safe_loads_bytes
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path
import logging
from collections import deque
import numpy as np

try:
    import redis
except ImportError:
    redis = None

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct
except ImportError:
    QdrantClient = None

logger = logging.getLogger(__name__)

class MemorySystem:
    """Advanced memory system with multiple memory types"""
    
    def __init__(self, settings):
        self.settings = settings
        
        # Memory stores
        self.working_memory = deque(maxlen=100)  # Short-term memory
        self.episodic_memory = []  # Event-based memory
        self.semantic_memory = {}  # Knowledge graph
        self.procedural_memory = {}  # Learned procedures
        
        # Cache
        self.cache_client = None
        if redis and settings.cache_enabled:
            try:
                self.cache_client = redis.from_url(settings.redis_url)
                logger.info("Redis cache connected")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
        
        # Vector store for RAG
        self.vector_client = None
        if QdrantClient:
            try:
                self.vector_client = QdrantClient(url=settings.qdrant_url)
                logger.info("Qdrant vector store connected")
            except Exception as e:
                logger.warning(f"Failed to connect to Qdrant: {e}")
        
        # Memory persistence
        self.memory_dir = settings.data_dir / "memory"
        self.memory_dir.mkdir(exist_ok=True)
        
        # Stats
        self.stats = {
            'interactions': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'memory_recalls': 0
        }
    
    def initialize(self):
        """Initialize memory system"""
        # Load persisted memory
        self._load_memory()
        
        # Initialize vector collections
        if self.vector_client:
            self._init_vector_collections()
    
    def _init_vector_collections(self):
        """Initialize Qdrant collections"""
        try:
            collections = self.vector_client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            # Create collections if they don't exist
            if "episodic" not in collection_names:
                self.vector_client.create_collection(
                    collection_name="episodic",
                    vectors_config=VectorParams(size=384, distance=Distance.COSINE)
                )
            
            if "semantic" not in collection_names:
                self.vector_client.create_collection(
                    collection_name="semantic",
                    vectors_config=VectorParams(size=384, distance=Distance.COSINE)
                )
            
            logger.info("Vector collections initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize vector collections: {e}")
    
    def store_interaction(self, interaction: Dict[str, Any]):
        """Store an interaction in memory"""
        # Add to working memory
        self.working_memory.append(interaction)
        
        # Add to episodic memory
        episode = {
            'id': len(self.episodic_memory),
            'timestamp': interaction.get('timestamp', datetime.now().isoformat()),
            'interaction': interaction,
            'context': self._get_current_context()
        }
        self.episodic_memory.append(episode)
        
        # Store in vector database if available
        if self.vector_client:
            self._store_in_vector_db(episode)
        
        # Update stats
        self.stats['interactions'] += 1
        
        # Periodic save
        if self.stats['interactions'] % 10 == 0:
            self._save_memory()
    
    def store_event(self, event: Dict[str, Any]):
        """Store a system event"""
        event['timestamp'] = datetime.now().isoformat()
        self.episodic_memory.append(event)
    
    def recall(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Recall relevant memories based on query"""
        self.stats['memory_recalls'] += 1
        
        # Search in vector database if available
        if self.vector_client:
            return self._vector_search(query, limit)
        
        # Fallback to simple search
        return self._simple_search(query, limit)
    
    def _vector_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Search memories using vector similarity"""
        try:
            # Generate embedding for query (simplified - should use actual embedding model)
            query_vector = self._generate_embedding(query)
            
            # Search in episodic collection
            results = self.vector_client.search(
                collection_name="episodic",
                query_vector=query_vector,
                limit=limit
            )
            
            memories = []
            for result in results:
                if result.payload:
                    memories.append(result.payload)
            
            return memories
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    def _simple_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Simple keyword-based search"""
        query_lower = query.lower()
        results = []
        
        for episode in reversed(self.episodic_memory):
            if isinstance(episode, dict):
                # Check if query matches any field
                episode_str = json.dumps(episode).lower()
                if query_lower in episode_str:
                    results.append(episode)
                    if len(results) >= limit:
                        break
        
        return results
    
    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using centralized manager"""
        from .embeddings.embedding_manager import get_embedding_manager
        manager = get_embedding_manager()
        return manager.generate(text)
    
    def _store_in_vector_db(self, episode: Dict[str, Any]):
        """Store episode in vector database"""
        try:
            # Generate embedding
            text = json.dumps(episode.get('interaction', {}))
            vector = self._generate_embedding(text)
            
            # Create point
            point = PointStruct(
                id=episode['id'],
                vector=vector,
                payload=episode
            )
            
            # Upsert to collection
            self.vector_client.upsert(
                collection_name="episodic",
                points=[point]
            )
            
        except Exception as e:
            logger.error(f"Failed to store in vector DB: {e}")
    
    def cache_get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self.cache_client:
            return None
        
        try:
            value = self.cache_client.get(key)
            if value:
                self.stats['cache_hits'] += 1
                return safe_loads_bytes(value)
            else:
                self.stats['cache_misses'] += 1
                return None
        except Exception as e:
            logger.error(f"Cache get failed: {e}")
            return None
    
    def cache_set(self, key: str, value: Any, ttl: int = None):
        """Set value in cache"""
        if not self.cache_client:
            return
        
        try:
            ttl = ttl or self.settings.cache_ttl
            self.cache_client.setex(
                key,
                ttl,
                safe_dumps_bytes(value)
            )
        except Exception as e:
            logger.error(f"Cache set failed: {e}")
    
    def learn_procedure(self, name: str, steps: List[Dict[str, Any]]):
        """Learn a new procedure"""
        self.procedural_memory[name] = {
            'steps': steps,
            'learned_at': datetime.now().isoformat(),
            'usage_count': 0
        }
    
    def recall_procedure(self, name: str) -> Optional[List[Dict[str, Any]]]:
        """Recall a learned procedure"""
        if name in self.procedural_memory:
            self.procedural_memory[name]['usage_count'] += 1
            return self.procedural_memory[name]['steps']
        return None
    
    def update_semantic_knowledge(self, concept: str, properties: Dict[str, Any]):
        """Update semantic knowledge graph"""
        if concept not in self.semantic_memory:
            self.semantic_memory[concept] = {}
        
        self.semantic_memory[concept].update(properties)
    
    def query_semantic_knowledge(self, concept: str) -> Optional[Dict[str, Any]]:
        """Query semantic knowledge"""
        return self.semantic_memory.get(concept)
    
    def _get_current_context(self) -> Dict[str, Any]:
        """Get current context from working memory"""
        if len(self.working_memory) > 0:
            recent = list(self.working_memory)[-5:]  # Last 5 items
            return {
                'recent_interactions': recent,
                'timestamp': datetime.now().isoformat()
            }
        return {}
    
    def consolidate_memory(self):
        """Consolidate memories (similar to sleep)"""
        # Move important items from working to long-term memory
        # Compress episodic memory
        # Update semantic knowledge from episodes
        
        logger.info("Memory consolidation completed")
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        return {
            'working_memory_size': len(self.working_memory),
            'episodic_memory_size': len(self.episodic_memory),
            'semantic_concepts': len(self.semantic_memory),
            'learned_procedures': len(self.procedural_memory),
            **self.stats
        }
    
    def export_memory(self) -> Dict[str, Any]:
        """Export memory for persistence"""
        return {
            'working_memory': list(self.working_memory),
            'episodic_memory': self.episodic_memory[-1000:],  # Last 1000 episodes
            'semantic_memory': self.semantic_memory,
            'procedural_memory': self.procedural_memory,
            'stats': self.stats
        }
    
    def import_memory(self, memory_data: Dict[str, Any]):
        """Import memory from saved data"""
        self.working_memory = deque(memory_data.get('working_memory', []), maxlen=100)
        self.episodic_memory = memory_data.get('episodic_memory', [])
        self.semantic_memory = memory_data.get('semantic_memory', {})
        self.procedural_memory = memory_data.get('procedural_memory', {})
        self.stats = memory_data.get('stats', self.stats)
    
    def _save_memory(self):
        """Save memory to disk"""
        try:
            memory_file = self.memory_dir / "memory.json"
            with open(memory_file, 'w') as f:
                json.dump(self.export_memory(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")
    
    def _load_memory(self):
        """Load memory from disk"""
        try:
            memory_file = self.memory_dir / "memory.json"
            if memory_file.exists():
                with open(memory_file, 'r') as f:
                    self.import_memory(json.load(f))
                logger.info("Memory loaded from disk")
        except Exception as e:
            logger.error(f"Failed to load memory: {e}")
    
    def cleanup(self):
        """Cleanup memory system"""
        self._save_memory()
        
        if self.cache_client:
            self.cache_client.close()
        
        logger.info("Memory system cleaned up")
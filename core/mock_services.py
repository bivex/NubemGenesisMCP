#!/usr/bin/env python3
"""
Mock Services for Development without Docker
Provides in-memory implementations of Redis, Vector DB, and other services
"""

import json
import time
import hashlib
from typing import Any, Dict, List, Optional, Tuple
from collections import OrderedDict, defaultdict
import asyncio
import logging
import numpy as np
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MockRedis:
    """
    In-memory Redis mock for development
    Supports basic operations: get, set, delete, exists, expire
    """
    
    def __init__(self):
        self.data: Dict[str, Any] = {}
        self.expiry: Dict[str, float] = {}
        self.lock = asyncio.Lock()
        logger.info("MockRedis initialized (in-memory)")
    
    async def get(self, key: str) -> Optional[bytes]:
        """Get value by key"""
        async with self.lock:
            # Check expiry
            if key in self.expiry:
                if time.time() > self.expiry[key]:
                    del self.data[key]
                    del self.expiry[key]
                    return None
            
            value = self.data.get(key)
            if value is not None:
                if isinstance(value, str):
                    return value.encode()
                return value
            return None
    
    async def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """Set key-value pair with optional expiry"""
        async with self.lock:
            if isinstance(value, bytes):
                value = value.decode()
            
            self.data[key] = value
            
            if ex:
                self.expiry[key] = time.time() + ex
            
            return True
    
    async def setex(self, key: str, seconds: int, value: Any) -> bool:
        """Set with expiry"""
        return await self.set(key, value, ex=seconds)
    
    async def delete(self, *keys: str) -> int:
        """Delete keys"""
        async with self.lock:
            deleted = 0
            for key in keys:
                if key in self.data:
                    del self.data[key]
                    if key in self.expiry:
                        del self.expiry[key]
                    deleted += 1
            return deleted
    
    async def exists(self, *keys: str) -> int:
        """Check if keys exist"""
        async with self.lock:
            count = 0
            for key in keys:
                if key in self.data:
                    # Check expiry
                    if key in self.expiry:
                        if time.time() > self.expiry[key]:
                            del self.data[key]
                            del self.expiry[key]
                            continue
                    count += 1
            return count
    
    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiry for key"""
        async with self.lock:
            if key in self.data:
                self.expiry[key] = time.time() + seconds
                return True
            return False
    
    async def ttl(self, key: str) -> int:
        """Get time to live for key"""
        async with self.lock:
            if key in self.expiry:
                ttl = int(self.expiry[key] - time.time())
                return max(ttl, 0)
            if key in self.data:
                return -1  # Key exists but has no expiry
            return -2  # Key does not exist
    
    async def flushdb(self) -> bool:
        """Clear all data"""
        async with self.lock:
            self.data.clear()
            self.expiry.clear()
            return True
    
    async def ping(self) -> str:
        """Check connection"""
        return "PONG"
    
    # Compatibility methods
    async def close(self):
        """Close connection (no-op for mock)"""
        pass
    
    def __repr__(self):
        return f"MockRedis(keys={len(self.data)})"


class MockVectorDB:
    """
    In-memory Vector Database mock for development
    Supports basic vector operations: store, search, delete
    """
    
    def __init__(self, collection_name: str = "default", dim: int = 768):
        self.collection_name = collection_name
        self.dim = dim
        self.vectors: Dict[str, Dict[str, Any]] = {}
        self.lock = asyncio.Lock()
        logger.info(f"MockVectorDB initialized: {collection_name} (dim={dim})")
    
    async def add_vectors(
        self,
        ids: List[str],
        vectors: List[List[float]],
        payloads: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """Add vectors to collection"""
        async with self.lock:
            if payloads is None:
                payloads = [{}] * len(ids)
            
            for id_, vector, payload in zip(ids, vectors, payloads):
                self.vectors[id_] = {
                    "vector": np.array(vector),
                    "payload": payload,
                    "timestamp": time.time()
                }
            
            logger.debug(f"Added {len(ids)} vectors to {self.collection_name}")
            return True
    
    async def search(
        self,
        query_vector: List[float],
        limit: int = 5,
        score_threshold: Optional[float] = None
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """Search for similar vectors"""
        async with self.lock:
            if not self.vectors:
                return []
            
            query = np.array(query_vector)
            results = []
            
            # Calculate cosine similarity for all vectors
            for id_, data in self.vectors.items():
                vector = data["vector"]
                
                # Cosine similarity
                similarity = np.dot(query, vector) / (
                    np.linalg.norm(query) * np.linalg.norm(vector) + 1e-8
                )
                
                if score_threshold is None or similarity >= score_threshold:
                    results.append((id_, float(similarity), data["payload"]))
            
            # Sort by similarity and return top k
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:limit]
    
    async def get_vector(self, id_: str) -> Optional[Dict[str, Any]]:
        """Get vector by ID"""
        async with self.lock:
            if id_ in self.vectors:
                data = self.vectors[id_]
                return {
                    "id": id_,
                    "vector": data["vector"].tolist(),
                    "payload": data["payload"]
                }
            return None
    
    async def delete_vectors(self, ids: List[str]) -> int:
        """Delete vectors by IDs"""
        async with self.lock:
            deleted = 0
            for id_ in ids:
                if id_ in self.vectors:
                    del self.vectors[id_]
                    deleted += 1
            return deleted
    
    async def count(self) -> int:
        """Count vectors in collection"""
        async with self.lock:
            return len(self.vectors)
    
    async def clear(self) -> bool:
        """Clear all vectors"""
        async with self.lock:
            self.vectors.clear()
            return True
    
    def __repr__(self):
        return f"MockVectorDB(collection={self.collection_name}, vectors={len(self.vectors)})"


class MockDatabase:
    """
    In-memory SQL database mock for development
    Simple key-value store with table support
    """
    
    def __init__(self):
        self.tables: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
        self.lock = asyncio.Lock()
        logger.info("MockDatabase initialized (in-memory)")
    
    async def create_table(self, table_name: str, schema: Dict[str, str]) -> bool:
        """Create a table"""
        async with self.lock:
            if table_name not in self.tables:
                self.tables[table_name] = {}
                logger.debug(f"Created table: {table_name}")
                return True
            return False
    
    async def insert(self, table_name: str, id_: str, data: Dict[str, Any]) -> bool:
        """Insert row into table"""
        async with self.lock:
            self.tables[table_name][id_] = {
                **data,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            return True
    
    async def select(
        self,
        table_name: str,
        where: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Select rows from table"""
        async with self.lock:
            results = []
            
            for id_, row in self.tables[table_name].items():
                if where:
                    # Simple equality check
                    match = all(row.get(k) == v for k, v in where.items())
                    if not match:
                        continue
                
                results.append({"id": id_, **row})
            
            if limit:
                results = results[:limit]
            
            return results
    
    async def update(
        self,
        table_name: str,
        id_: str,
        data: Dict[str, Any]
    ) -> bool:
        """Update row in table"""
        async with self.lock:
            if id_ in self.tables[table_name]:
                self.tables[table_name][id_].update(data)
                self.tables[table_name][id_]["updated_at"] = datetime.now().isoformat()
                return True
            return False
    
    async def delete(self, table_name: str, id_: str) -> bool:
        """Delete row from table"""
        async with self.lock:
            if id_ in self.tables[table_name]:
                del self.tables[table_name][id_]
                return True
            return False
    
    def __repr__(self):
        return f"MockDatabase(tables={list(self.tables.keys())})"


class ServiceFactory:
    """
    Factory for creating mock or real services based on configuration
    """
    
    _instances = {}
    
    @classmethod
    def get_redis(cls, use_mock: bool = None) -> Any:
        """Get Redis client (mock or real)"""
        if use_mock is None:
            # Auto-detect based on environment
            import os
            use_mock = os.getenv("ENABLE_REDIS", "false").lower() == "false"
        
        if use_mock:
            if "mock_redis" not in cls._instances:
                cls._instances["mock_redis"] = MockRedis()
            return cls._instances["mock_redis"]
        else:
            # Try to return real Redis client
            try:
                import redis.asyncio as redis
                if "real_redis" not in cls._instances:
                    cls._instances["real_redis"] = redis.Redis(
                        host=os.getenv("REDIS_HOST", "localhost"),
                        port=int(os.getenv("REDIS_PORT", 6379)),
                        decode_responses=True
                    )
                return cls._instances["real_redis"]
            except ImportError:
                logger.warning("Redis not installed, using mock")
                return cls.get_redis(use_mock=True)
    
    @classmethod
    def get_vector_db(cls, use_mock: bool = None) -> Any:
        """Get Vector DB client (mock or real)"""
        if use_mock is None:
            import os
            use_mock = os.getenv("ENABLE_VECTOR_DB", "false").lower() == "false"
        
        if use_mock:
            if "mock_vector" not in cls._instances:
                cls._instances["mock_vector"] = MockVectorDB()
            return cls._instances["mock_vector"]
        else:
            # Try to return real Qdrant client
            try:
                from qdrant_client import QdrantClient
                if "real_vector" not in cls._instances:
                    cls._instances["real_vector"] = QdrantClient(
                        host=os.getenv("QDRANT_HOST", "localhost"),
                        port=int(os.getenv("QDRANT_PORT", 6333))
                    )
                return cls._instances["real_vector"]
            except ImportError:
                logger.warning("Qdrant not installed, using mock")
                return cls.get_vector_db(use_mock=True)
    
    @classmethod
    def get_database(cls, use_mock: bool = None) -> Any:
        """Get Database client (mock or real)"""
        if use_mock is None:
            import os
            use_mock = os.getenv("DATABASE_URL", "").startswith("sqlite")
        
        if use_mock:
            if "mock_database" not in cls._instances:
                cls._instances["mock_database"] = MockDatabase()
            return cls._instances["mock_database"]
        else:
            # Return real database connection
            # This would be your actual database client
            return None


# Convenience functions
def get_redis_client():
    """Get Redis client (auto-detects mock vs real)"""
    return ServiceFactory.get_redis()

def get_vector_db():
    """Get Vector DB client (auto-detects mock vs real)"""
    return ServiceFactory.get_vector_db()

def get_database():
    """Get Database client (auto-detects mock vs real)"""
    return ServiceFactory.get_database()


# Example usage
if __name__ == "__main__":
    async def test_mocks():
        # Test MockRedis
        redis = MockRedis()
        await redis.set("test_key", "test_value", ex=60)
        value = await redis.get("test_key")
        print(f"Redis test: {value}")
        
        # Test MockVectorDB
        vector_db = MockVectorDB()
        await vector_db.add_vectors(
            ids=["vec1", "vec2"],
            vectors=[[0.1] * 768, [0.2] * 768],
            payloads=[{"text": "Hello"}, {"text": "World"}]
        )
        results = await vector_db.search([0.15] * 768, limit=2)
        print(f"Vector search: {results}")
        
        # Test MockDatabase
        db = MockDatabase()
        await db.create_table("users", {"name": "string", "email": "string"})
        await db.insert("users", "user1", {"name": "Alice", "email": "alice@example.com"})
        users = await db.select("users")
        print(f"Database test: {users}")
    
    asyncio.run(test_mocks())
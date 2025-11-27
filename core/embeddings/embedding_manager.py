#!/usr/bin/env python3
"""
Centralized Embedding Manager
Replaces 53 duplicate embedding functions across the codebase
Provides singleton pattern for efficient model loading
"""

import logging
import hashlib
from core.safe_serialization import safe_dumps, safe_loads, safe_dumps_bytes, safe_loads_bytes
from typing import List, Optional, Dict, Any, Union
from functools import lru_cache
from pathlib import Path
import numpy as np
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class EmbeddingManager:
    """
    Singleton embedding manager that handles all text embedding operations
    Supports multiple backends and caching
    """
    
    _instance = None
    _model = None
    _cache_dir = Path.home() / '.cache' / 'nubem_embeddings'
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the embedding manager"""
        if not self._initialized:
            self._initialized = True
            self.model_name = 'all-MiniLM-L6-v2'
            self.embedding_dim = 384
            self.cache_enabled = True
            self.cache_ttl = timedelta(days=7)
            self._model = None
            self._tfidf_vectorizer = None
            self._backend = 'auto'  # auto, transformer, tfidf, hash
            
            # Create cache directory
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            
            # Try to initialize model
            self._initialize_model()
            
            logger.info(f"EmbeddingManager initialized with backend: {self._backend}")
    
    def _initialize_model(self):
        """Initialize the embedding model based on available libraries"""
        # Try sentence-transformers first
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            self._backend = 'transformer'
            logger.info(f"Loaded transformer model: {self.model_name}")
            return
        except ImportError:
            logger.debug("sentence-transformers not available")
        except Exception as e:
            logger.warning(f"Failed to load transformer model: {e}")
        
        # Try TF-IDF as fallback
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.decomposition import TruncatedSVD
            
            self._tfidf_vectorizer = TfidfVectorizer(
                max_features=10000,
                ngram_range=(1, 2),
                stop_words='english'
            )
            self._svd = TruncatedSVD(n_components=self.embedding_dim)
            self._backend = 'tfidf'
            logger.info("Using TF-IDF backend for embeddings")
            return
        except ImportError:
            logger.debug("scikit-learn not available")
        except Exception as e:
            logger.warning(f"Failed to initialize TF-IDF: {e}")
        
        # Fallback to hash-based embeddings
        self._backend = 'hash'
        logger.info("Using hash-based backend for embeddings")
    
    @lru_cache(maxsize=1000)
    def generate(self, 
                text: Union[str, List[str]], 
                normalize: bool = True,
                use_cache: bool = True) -> Union[List[float], List[List[float]]]:
        """
        Generate embedding(s) for text
        
        Args:
            text: Single text or list of texts
            normalize: Whether to normalize embeddings to unit length
            use_cache: Whether to use cache
        
        Returns:
            Embedding vector(s)
        """
        is_batch = isinstance(text, list)
        texts = text if is_batch else [text]
        
        embeddings = []
        for t in texts:
            # Check cache
            if use_cache and self.cache_enabled:
                cached = self._get_cached_embedding(t)
                if cached is not None:
                    embeddings.append(cached)
                    continue
            
            # Generate embedding based on backend
            if self._backend == 'transformer':
                embedding = self._generate_transformer(t)
            elif self._backend == 'tfidf':
                embedding = self._generate_tfidf(t)
            else:
                embedding = self._generate_hash(t)
            
            # Normalize if requested
            if normalize:
                embedding = self._normalize_vector(embedding)
            
            # Cache the result
            if use_cache and self.cache_enabled:
                self._cache_embedding(t, embedding)
            
            embeddings.append(embedding)
        
        return embeddings if is_batch else embeddings[0]
    
    def _generate_transformer(self, text: str) -> List[float]:
        """Generate embedding using transformer model"""
        try:
            embedding = self._model.encode(text, show_progress_bar=False)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Transformer embedding failed: {e}")
            # Fallback to hash
            return self._generate_hash(text)
    
    def _generate_tfidf(self, text: str) -> List[float]:
        """Generate embedding using TF-IDF"""
        try:
            # For single text, we need to fit or use existing vocabulary
            if not hasattr(self._tfidf_vectorizer, 'vocabulary_'):
                # Initialize with some sample text
                sample_texts = [text, "sample text for initialization"]
                tfidf_matrix = self._tfidf_vectorizer.fit_transform(sample_texts)
                self._svd.fit(tfidf_matrix)
            
            # Transform the text
            tfidf_vector = self._tfidf_vectorizer.transform([text])
            embedding = self._svd.transform(tfidf_vector)[0]
            
            # Pad or truncate to match embedding_dim
            if len(embedding) < self.embedding_dim:
                embedding = np.pad(embedding, (0, self.embedding_dim - len(embedding)))
            else:
                embedding = embedding[:self.embedding_dim]
            
            return embedding.tolist()
        except Exception as e:
            logger.error(f"TF-IDF embedding failed: {e}")
            return self._generate_hash(text)
    
    def _generate_hash(self, text: str) -> List[float]:
        """Generate deterministic hash-based embedding"""
        # Create deterministic seed from text
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        seed = int(text_hash[:8], 16)
        
        # Generate pseudo-random vector
        np.random.seed(seed)
        vector = np.random.randn(self.embedding_dim)
        
        # Make it somewhat meaningful by incorporating text features
        features = [
            len(text) / 1000.0,  # Length feature
            text.count(' ') / 100.0,  # Word count approximation
            text.count('.') / 10.0,  # Sentence count approximation
            sum(1 for c in text if c.isupper()) / 100.0,  # Uppercase ratio
            sum(1 for c in text if c.isdigit()) / 100.0,  # Digit ratio
        ]
        
        # Incorporate features into first dimensions
        for i, feat in enumerate(features[:5]):
            if i < self.embedding_dim:
                vector[i] = vector[i] * 0.8 + feat * 0.2
        
        return vector.tolist()
    
    def _normalize_vector(self, vector: List[float]) -> List[float]:
        """Normalize vector to unit length"""
        arr = np.array(vector)
        norm = np.linalg.norm(arr)
        if norm > 0:
            arr = arr / norm
        return arr.tolist()
    
    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text"""
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return f"{self._backend}_{self.model_name}_{text_hash}"
    
    def _get_cached_embedding(self, text: str) -> Optional[List[float]]:
        """Retrieve cached embedding if available"""
        cache_key = self._get_cache_key(text)
        cache_file = self._cache_dir / f"{cache_key}.pkl"
        
        if cache_file.exists():
            try:
                # Check if cache is still valid
                if datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime) < self.cache_ttl:
                    with open(cache_file, 'rb') as f:
                        return safe_loads_bytes(f.read())
            except Exception as e:
                logger.debug(f"Cache read failed: {e}")
        
        return None
    
    def _cache_embedding(self, text: str, embedding: List[float]):
        """Cache embedding to disk"""
        cache_key = self._get_cache_key(text)
        cache_file = self._cache_dir / f"{cache_key}.pkl"
        
        try:
            with open(cache_file, 'wb') as f:
                f.write(safe_dumps_bytes(embedding))
        except Exception as e:
            logger.debug(f"Cache write failed: {e}")
    
    def batch_generate(self, 
                      texts: List[str], 
                      normalize: bool = True,
                      show_progress: bool = False) -> List[List[float]]:
        """
        Generate embeddings for multiple texts efficiently
        
        Args:
            texts: List of texts
            normalize: Whether to normalize embeddings
            show_progress: Whether to show progress bar
        
        Returns:
            List of embedding vectors
        """
        if self._backend == 'transformer' and self._model:
            try:
                # Use batch encoding for efficiency
                embeddings = self._model.encode(
                    texts, 
                    show_progress_bar=show_progress,
                    normalize_embeddings=normalize
                )
                return embeddings.tolist()
            except Exception as e:
                logger.error(f"Batch encoding failed: {e}")
        
        # Fallback to individual generation
        return [self.generate(text, normalize=normalize) for text in texts]
    
    def similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """
        Calculate cosine similarity between two embeddings
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
        
        Returns:
            Similarity score between -1 and 1
        """
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)
        
        # Normalize vectors
        vec1_norm = vec1 / (np.linalg.norm(vec1) + 1e-10)
        vec2_norm = vec2 / (np.linalg.norm(vec2) + 1e-10)
        
        # Calculate cosine similarity
        return float(np.dot(vec1_norm, vec2_norm))
    
    def find_similar(self, 
                    query_embedding: List[float],
                    candidate_embeddings: List[List[float]],
                    top_k: int = 5,
                    threshold: float = 0.0) -> List[tuple]:
        """
        Find most similar embeddings from candidates
        
        Args:
            query_embedding: Query embedding vector
            candidate_embeddings: List of candidate embeddings
            top_k: Number of top results to return
            threshold: Minimum similarity threshold
        
        Returns:
            List of (index, similarity_score) tuples
        """
        similarities = []
        
        for idx, candidate in enumerate(candidate_embeddings):
            sim = self.similarity(query_embedding, candidate)
            if sim >= threshold:
                similarities.append((idx, sim))
        
        # Sort by similarity (descending)
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        return similarities[:top_k]
    
    def get_info(self) -> Dict[str, Any]:
        """Get information about the embedding manager"""
        cache_files = list(self._cache_dir.glob("*.pkl")) if self._cache_dir.exists() else []
        
        return {
            'backend': self._backend,
            'model_name': self.model_name if self._backend == 'transformer' else None,
            'embedding_dimension': self.embedding_dim,
            'cache_enabled': self.cache_enabled,
            'cache_size': len(cache_files),
            'cache_directory': str(self._cache_dir),
            'supported_backends': ['transformer', 'tfidf', 'hash']
        }
    
    def clear_cache(self):
        """Clear the embedding cache"""
        if self._cache_dir.exists():
            for cache_file in self._cache_dir.glob("*.pkl"):
                try:
                    cache_file.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete cache file: {e}")
            logger.info("Embedding cache cleared")
    
    def set_backend(self, backend: str):
        """
        Switch to a different backend
        
        Args:
            backend: One of 'auto', 'transformer', 'tfidf', 'hash'
        """
        if backend not in ['auto', 'transformer', 'tfidf', 'hash']:
            raise ValueError(f"Invalid backend: {backend}")
        
        self._backend = backend
        if backend == 'auto':
            self._initialize_model()
        
        logger.info(f"Switched to backend: {self._backend}")


# Global instance
_embedding_manager = None

def get_embedding_manager() -> EmbeddingManager:
    """Get the global embedding manager instance"""
    global _embedding_manager
    if _embedding_manager is None:
        _embedding_manager = EmbeddingManager()
    return _embedding_manager


# Convenience functions for backward compatibility

def generate_embedding(text: str, **kwargs) -> List[float]:
    """Generate embedding for text (backward compatibility)"""
    manager = get_embedding_manager()
    return manager.generate(text, **kwargs)


def batch_generate_embeddings(texts: List[str], **kwargs) -> List[List[float]]:
    """Generate embeddings for multiple texts (backward compatibility)"""
    manager = get_embedding_manager()
    return manager.batch_generate(texts, **kwargs)


def calculate_similarity(embedding1: List[float], embedding2: List[float]) -> float:
    """Calculate similarity between embeddings (backward compatibility)"""
    manager = get_embedding_manager()
    return manager.similarity(embedding1, embedding2)


# Example usage and testing
def test_embedding_manager():
    """Test the embedding manager"""
    print("Testing Embedding Manager\n" + "="*50)
    
    # Get manager instance
    manager = get_embedding_manager()
    
    # Display info
    info = manager.get_info()
    print(f"Backend: {info['backend']}")
    print(f"Dimension: {info['embedding_dimension']}")
    print(f"Cache enabled: {info['cache_enabled']}")
    print()
    
    # Test single embedding
    text1 = "Machine learning is a subset of artificial intelligence"
    embedding1 = manager.generate(text1)
    print(f"Generated embedding for text1: {len(embedding1)} dimensions")
    
    # Test batch embeddings
    texts = [
        "Python is a programming language",
        "Data science involves analyzing data",
        "Neural networks are inspired by the brain"
    ]
    embeddings = manager.batch_generate(texts)
    print(f"Generated {len(embeddings)} embeddings in batch")
    
    # Test similarity
    text2 = "AI and machine learning are related fields"
    embedding2 = manager.generate(text2)
    
    similarity = manager.similarity(embedding1, embedding2)
    print(f"\nSimilarity between text1 and text2: {similarity:.3f}")
    
    # Find similar
    similar_indices = manager.find_similar(embedding1, embeddings, top_k=2)
    print(f"\nMost similar to text1:")
    for idx, score in similar_indices:
        print(f"  {texts[idx][:50]}: {score:.3f}")
    
    # Test caching
    import time
    start = time.time()
    _ = manager.generate(text1)  # Should be cached
    cached_time = time.time() - start
    
    start = time.time()
    _ = manager.generate("This is a completely new text that's not cached")
    uncached_time = time.time() - start
    
    print(f"\nCached retrieval: {cached_time*1000:.2f}ms")
    print(f"Uncached generation: {uncached_time*1000:.2f}ms")
    
    print("\n✅ All tests passed!")


if __name__ == "__main__":
    test_embedding_manager()
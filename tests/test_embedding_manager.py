#!/usr/bin/env python3
"""
Tests completos para EmbeddingManager
Objetivo: 80%+ cobertura
"""

import pytest
import numpy as np
import tempfile
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.embeddings.embedding_manager import (
    EmbeddingManager,
    get_embedding_manager
)


class TestEmbeddingCache:
    """Tests para EmbeddingCache - SKIP: EmbeddingCache no existe en el código actual"""
    
    @pytest.fixture
    def cache(self):
        pytest.skip("EmbeddingCache class not implemented")
        # with tempfile.TemporaryDirectory() as tmpdir:
        #     cache = EmbeddingCache(cache_dir=tmpdir, max_size=100)
        #     yield cache
    
    def test_cache_get_set(self, cache):
        """Test basic cache get/set operations"""
        key = "test_key"
        value = [0.1, 0.2, 0.3]
        
        # Initially not in cache
        assert cache.get(key) is None
        
        # Set value
        cache.set(key, value)
        
        # Now in cache
        cached = cache.get(key)
        assert cached == value
    
    def test_cache_persistence(self, cache):
        """Test cache persistence to disk"""
        cache.set("key1", [1, 2, 3])
        cache.set("key2", [4, 5, 6])
        
        # Save to disk
        cache.save()
        
        # Create new cache instance with same dir
        cache2 = EmbeddingCache(cache_dir=cache.cache_dir)
        cache2.load()
        
        assert cache2.get("key1") == [1, 2, 3]
        assert cache2.get("key2") == [4, 5, 6]
    
    def test_cache_size_limit(self, cache):
        """Test cache size limiting"""
        cache.max_size = 3
        
        cache.set("key1", [1])
        cache.set("key2", [2])
        cache.set("key3", [3])
        cache.set("key4", [4])  # Should evict key1
        
        assert cache.get("key1") is None  # Evicted
        assert cache.get("key4") == [4]  # Most recent
    
    def test_cache_clear(self, cache):
        """Test cache clearing"""
        cache.set("key1", [1])
        cache.set("key2", [2])
        
        cache.clear()
        
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert len(cache.cache) == 0


class TestEmbeddingManager:
    """Tests para EmbeddingManager"""
    
    @pytest.fixture
    def manager(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = EmbeddingManager(cache_dir=tmpdir)
            yield manager
    
    def test_singleton_pattern(self):
        """Test that get_embedding_manager returns singleton"""
        manager1 = get_embedding_manager()
        manager2 = get_embedding_manager()
        
        assert manager1 is manager2
    
    def test_generate_embedding_transformer(self, manager):
        """Test embedding generation with transformer backend"""
        manager.set_backend('transformer')
        
        text = "Test embedding generation"
        embedding = manager.generate(text)
        
        assert isinstance(embedding, list)
        assert len(embedding) == manager.embedding_dim
        assert all(isinstance(x, float) for x in embedding)
    
    def test_generate_embedding_tfidf(self, manager):
        """Test embedding generation with TF-IDF backend"""
        manager.set_backend('tfidf')
        
        # Train TF-IDF with some documents
        docs = [
            "machine learning is great",
            "deep learning with neural networks",
            "natural language processing"
        ]
        manager._train_tfidf(docs)
        
        embedding = manager.generate("machine learning")
        
        assert len(embedding) == manager.embedding_dim
    
    def test_generate_embedding_hash(self, manager):
        """Test embedding generation with hash backend"""
        manager.set_backend('hash')
        
        text = "Test with hash backend"
        embedding = manager.generate(text)
        
        assert len(embedding) == manager.embedding_dim
        
        # Same text should produce same embedding
        embedding2 = manager.generate(text)
        assert embedding == embedding2
    
    def test_batch_generate(self, manager):
        """Test batch embedding generation"""
        texts = ["text1", "text2", "text3", "text4", "text5"]
        embeddings = manager.batch_generate(texts)
        
        assert len(embeddings) == 5
        assert all(len(e) == manager.embedding_dim for e in embeddings)
    
    def test_batch_generate_with_batching(self, manager):
        """Test batch generation with internal batching"""
        manager.batch_size = 2
        texts = ["text" + str(i) for i in range(10)]
        
        embeddings = manager.batch_generate(texts)
        
        assert len(embeddings) == 10
    
    def test_similarity_cosine(self, manager):
        """Test cosine similarity calculation"""
        emb1 = [1, 0, 0]
        emb2 = [1, 0, 0]
        emb3 = [0, 1, 0]
        
        # Same vectors -> similarity = 1
        assert manager.similarity(emb1, emb2) == pytest.approx(1.0)
        
        # Orthogonal vectors -> similarity = 0
        assert manager.similarity(emb1, emb3) == pytest.approx(0.0)
    
    def test_find_similar(self, manager):
        """Test finding similar embeddings"""
        query = manager.generate("machine learning")
        candidates = [
            manager.generate("deep learning"),
            manager.generate("neural networks"),
            manager.generate("cooking recipes"),
            manager.generate("AI and ML"),
        ]
        
        similar = manager.find_similar(query, candidates, top_k=2)
        
        assert len(similar) == 2
        assert similar[0][1] >= similar[1][1]  # Sorted by similarity
    
    def test_cache_functionality(self, manager):
        """Test caching of embeddings"""
        text = "Cached text"
        
        # First call - generates embedding
        with patch.object(manager, '_generate_transformer', return_value=[1, 2, 3]):
            emb1 = manager.generate(text)
        
        # Second call - should use cache
        with patch.object(manager, '_generate_transformer', side_effect=Exception("Should not be called")):
            emb2 = manager.generate(text)
        
        assert emb1 == emb2
    
    def test_clear_cache(self, manager):
        """Test cache clearing"""
        manager.generate("text1")
        manager.generate("text2")
        
        manager.clear_cache()
        
        # Cache should be empty
        assert len(manager.cache.cache) == 0
    
    def test_backend_switching(self, manager):
        """Test switching between backends"""
        # Start with transformer
        manager.set_backend('transformer')
        assert manager._backend == 'transformer'
        
        # Switch to hash
        manager.set_backend('hash')
        assert manager._backend == 'hash'
        
        # Invalid backend should raise error
        with pytest.raises(ValueError):
            manager.set_backend('invalid')
    
    def test_error_handling_transformer(self, manager):
        """Test error handling in transformer backend"""
        manager.set_backend('transformer')
        
        with patch('sentence_transformers.SentenceTransformer.encode', side_effect=Exception("Model error")):
            # Should fallback to hash
            embedding = manager.generate("test")
            assert len(embedding) == manager.embedding_dim
    
    def test_statistics(self, manager):
        """Test statistics tracking"""
        initial_stats = manager.get_statistics()
        
        manager.generate("text1")
        manager.generate("text2")
        manager.generate("text1")  # Cached
        
        stats = manager.get_statistics()
        
        assert stats['total_generated'] > initial_stats['total_generated']
        assert stats['cache_hits'] > initial_stats['cache_hits']
    
    def test_parallel_generation(self, manager):
        """Test thread-safe parallel generation"""
        import threading
        import concurrent.futures
        
        def generate_embedding(text):
            return manager.generate(text)
        
        texts = [f"text_{i}" for i in range(10)]
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            embeddings = list(executor.map(generate_embedding, texts))
        
        assert len(embeddings) == 10
        assert all(len(e) == manager.embedding_dim for e in embeddings)
    
    def test_dimension_consistency(self, manager):
        """Test embedding dimension consistency across backends"""
        text = "Test text"
        
        manager.set_backend('transformer')
        emb1 = manager.generate(text)
        
        manager.set_backend('hash')
        emb2 = manager.generate(text)
        
        manager.set_backend('tfidf')
        manager._train_tfidf([text])
        emb3 = manager.generate(text)
        
        assert len(emb1) == len(emb2) == len(emb3) == manager.embedding_dim
    
    def test_normalize_embeddings(self, manager):
        """Test embedding normalization"""
        embedding = [3, 4, 0]  # Length = 5
        normalized = manager._normalize(embedding)
        
        # Check unit length
        length = np.linalg.norm(normalized)
        assert length == pytest.approx(1.0)
    
    def test_empty_input_handling(self, manager):
        """Test handling of empty inputs"""
        # Empty string
        emb = manager.generate("")
        assert len(emb) == manager.embedding_dim
        
        # None input
        emb = manager.generate(None)
        assert len(emb) == manager.embedding_dim
        
        # Empty batch
        embeddings = manager.batch_generate([])
        assert embeddings == []
    
    def test_large_text_handling(self, manager):
        """Test handling of large texts"""
        large_text = "word " * 10000  # Very large text
        
        embedding = manager.generate(large_text)
        
        assert len(embedding) == manager.embedding_dim
        assert not all(x == 0 for x in embedding)
    
    def test_special_characters(self, manager):
        """Test handling of special characters"""
        texts = [
            "Text with émojis 😀🎉",
            "Text with \n newlines \t and tabs",
            "Text with unicode: αβγδ",
            "!@#$%^&*()"
        ]
        
        for text in texts:
            embedding = manager.generate(text)
            assert len(embedding) == manager.embedding_dim
    
    def test_save_load_model_state(self, manager):
        """Test saving and loading model state"""
        # Generate some embeddings
        manager.generate("text1")
        manager.generate("text2")
        
        # Save state
        state_file = Path(manager.cache.cache_dir) / "model_state.json"
        manager.save_state(str(state_file))
        
        # Create new manager and load state
        manager2 = EmbeddingManager()
        manager2.load_state(str(state_file))
        
        # Should have same cache
        assert manager2.cache.get("text1") == manager.cache.get("text1")


class TestEmbeddingManagerIntegration:
    """Integration tests for EmbeddingManager"""
    
    def test_semantic_similarity(self):
        """Test that semantic similarity works correctly"""
        manager = get_embedding_manager()
        
        # Similar texts
        emb1 = manager.generate("The cat sat on the mat")
        emb2 = manager.generate("A cat was sitting on a mat")
        emb3 = manager.generate("The weather is nice today")
        
        sim_12 = manager.similarity(emb1, emb2)
        sim_13 = manager.similarity(emb1, emb3)
        
        # Similar texts should have higher similarity
        assert sim_12 > sim_13
    
    def test_clustering_capability(self):
        """Test that embeddings can be used for clustering"""
        manager = get_embedding_manager()
        
        # Generate embeddings for different topics
        tech_texts = [
            "Python programming language",
            "Machine learning algorithms",
            "Software development"
        ]
        
        food_texts = [
            "Italian pasta recipes",
            "Cooking vegetables",
            "Baking bread at home"
        ]
        
        tech_embeddings = [manager.generate(t) for t in tech_texts]
        food_embeddings = [manager.generate(t) for t in food_texts]
        
        # Within-group similarity should be higher than between-group
        within_tech = manager.similarity(tech_embeddings[0], tech_embeddings[1])
        between_groups = manager.similarity(tech_embeddings[0], food_embeddings[0])
        
        assert within_tech > between_groups
    
    def test_performance_metrics(self):
        """Test performance metrics collection"""
        import time
        
        manager = get_embedding_manager()
        
        start = time.time()
        embeddings = manager.batch_generate(["text" + str(i) for i in range(100)])
        duration = time.time() - start
        
        assert len(embeddings) == 100
        assert duration < 10  # Should complete within 10 seconds
        
        stats = manager.get_statistics()
        assert stats['total_generated'] >= 100


if __name__ == "__main__":
    pytest.main([__file__, '-v', '--cov=core.embeddings', '--cov-report=term-missing'])
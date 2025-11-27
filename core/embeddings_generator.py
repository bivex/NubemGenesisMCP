"""
Embeddings Generator - Sentence Transformers Integration
Generate embeddings for text using sentence-transformers models
"""

import logging
from typing import List, Dict, Any, Optional, Union
import numpy as np
from dataclasses import dataclass

# Lazy import to avoid Python 3.9 compatibility issues
SENTENCE_TRANSFORMERS_AVAILABLE = False
SentenceTransformer = None

def _try_import_sentence_transformers():
    """Lazy import of sentence-transformers"""
    global SENTENCE_TRANSFORMERS_AVAILABLE, SentenceTransformer
    try:
        from sentence_transformers import SentenceTransformer as ST
        SentenceTransformer = ST
        SENTENCE_TRANSFORMERS_AVAILABLE = True
        return True
    except (ImportError, TypeError) as e:
        SENTENCE_TRANSFORMERS_AVAILABLE = False
        logging.warning(f"sentence-transformers not available: {e}")
        return False

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """Result of embedding generation"""
    text: str
    embedding: List[float]
    model: str
    dimension: int
    metadata: Optional[Dict[str, Any]] = None


class EmbeddingsGenerator:
    """
    Generate embeddings using sentence-transformers

    Features:
    - Multiple model support (all-MiniLM-L6-v2, all-mpnet-base-v2, etc.)
    - Batch processing for efficiency
    - Caching for repeated texts
    - Normalization options
    - Compatible with Qdrant (768-dimensional vectors)
    """

    # Recommended models
    MODELS = {
        # Fast and efficient (default)
        'mini': 'all-MiniLM-L6-v2',  # 384 dimensions, fast
        'small': 'all-MiniLM-L12-v2',  # 384 dimensions, balanced

        # High quality
        'base': 'all-mpnet-base-v2',  # 768 dimensions, best quality
        'large': 'sentence-transformers/all-roberta-large-v1',  # 1024 dimensions

        # Multilingual
        'multilingual': 'paraphrase-multilingual-MiniLM-L12-v2',  # 384 dimensions

        # Code-specific
        'code': 'microsoft/codebert-base',  # 768 dimensions
    }

    def __init__(
        self,
        model_name: str = 'base',
        device: str = 'cpu',
        normalize_embeddings: bool = True,
        cache_enabled: bool = True
    ):
        """
        Initialize Embeddings Generator

        Args:
            model_name: Model to use ('mini', 'base', 'large', or full model name)
            device: Device to use ('cpu', 'cuda', 'mps')
            normalize_embeddings: Whether to normalize embeddings to unit length
            cache_enabled: Enable caching of embeddings
        """
        # Try lazy import
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            if not _try_import_sentence_transformers():
                raise ImportError("sentence-transformers not available (requires Python 3.10+)")

        # Resolve model name
        self.model_name = self.MODELS.get(model_name, model_name)
        self.device = device
        self.normalize_embeddings = normalize_embeddings
        self.cache_enabled = cache_enabled

        # Initialize cache
        self._cache: Dict[str, np.ndarray] = {}

        # Load model
        try:
            self.model = SentenceTransformer(self.model_name, device=device)
            self.dimension = self.model.get_sentence_embedding_dimension()
            logger.info(f"Loaded embedding model: {self.model_name} ({self.dimension}D) on {device}")
        except Exception as e:
            logger.error(f"Failed to load model {self.model_name}: {e}")
            raise

    def generate(
        self,
        text: Union[str, List[str]],
        batch_size: int = 32,
        show_progress: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Union[EmbeddingResult, List[EmbeddingResult]]:
        """
        Generate embeddings for text(s)

        Args:
            text: Single text or list of texts
            batch_size: Batch size for processing
            show_progress: Show progress bar
            metadata: Optional metadata to attach

        Returns:
            EmbeddingResult or list of EmbeddingResults
        """
        single_input = isinstance(text, str)
        texts = [text] if single_input else text

        # Check cache
        if self.cache_enabled:
            cached_results = []
            uncached_texts = []
            uncached_indices = []

            for idx, t in enumerate(texts):
                if t in self._cache:
                    embedding = self._cache[t]
                    cached_results.append((idx, embedding))
                else:
                    uncached_texts.append(t)
                    uncached_indices.append(idx)

            # Generate embeddings for uncached texts
            if uncached_texts:
                embeddings = self.model.encode(
                    uncached_texts,
                    batch_size=batch_size,
                    show_progress_bar=show_progress,
                    normalize_embeddings=self.normalize_embeddings,
                    convert_to_numpy=True
                )

                # Cache new embeddings
                for text, embedding in zip(uncached_texts, embeddings):
                    self._cache[text] = embedding

                # Merge cached and new results
                all_embeddings = [None] * len(texts)
                for idx, embedding in cached_results:
                    all_embeddings[idx] = embedding
                for idx, embedding in zip(uncached_indices, embeddings):
                    all_embeddings[idx] = embedding
            else:
                # All from cache
                all_embeddings = [None] * len(texts)
                for idx, embedding in cached_results:
                    all_embeddings[idx] = embedding
        else:
            # No caching
            all_embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=show_progress,
                normalize_embeddings=self.normalize_embeddings,
                convert_to_numpy=True
            )

        # Create results
        results = [
            EmbeddingResult(
                text=t,
                embedding=emb.tolist(),
                model=self.model_name,
                dimension=self.dimension,
                metadata=metadata
            )
            for t, emb in zip(texts, all_embeddings)
        ]

        return results[0] if single_input else results

    def generate_for_documents(
        self,
        documents: List[Dict[str, str]],
        text_field: str = 'content',
        batch_size: int = 32
    ) -> List[EmbeddingResult]:
        """
        Generate embeddings for a list of documents

        Args:
            documents: List of document dictionaries
            text_field: Field containing text to embed
            batch_size: Batch size for processing

        Returns:
            List of EmbeddingResults
        """
        texts = [doc[text_field] for doc in documents]
        metadatas = [{k: v for k, v in doc.items() if k != text_field} for doc in documents]

        results = self.generate(texts, batch_size=batch_size)

        # Add metadata
        for result, metadata in zip(results, metadatas):
            result.metadata = metadata

        return results

    def similarity(
        self,
        text1: str,
        text2: str
    ) -> float:
        """
        Calculate cosine similarity between two texts

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score (0-1)
        """
        embeddings = self.generate([text1, text2])
        emb1 = np.array(embeddings[0].embedding)
        emb2 = np.array(embeddings[1].embedding)

        # Cosine similarity
        similarity = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
        return float(similarity)

    def find_most_similar(
        self,
        query: str,
        candidates: List[str],
        top_k: int = 5
    ) -> List[tuple[str, float]]:
        """
        Find most similar texts to a query

        Args:
            query: Query text
            candidates: List of candidate texts
            top_k: Number of top results to return

        Returns:
            List of (text, score) tuples
        """
        # Generate embeddings
        results = self.generate([query] + candidates)
        query_emb = np.array(results[0].embedding)
        candidate_embs = np.array([r.embedding for r in results[1:]])

        # Calculate similarities
        similarities = np.dot(candidate_embs, query_emb)

        # Get top k
        top_indices = np.argsort(similarities)[::-1][:top_k]
        top_results = [(candidates[i], float(similarities[i])) for i in top_indices]

        return top_results

    def clear_cache(self):
        """Clear embedding cache"""
        self._cache.clear()
        logger.info("Embedding cache cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return {
            'size': len(self._cache),
            'total_bytes': sum(emb.nbytes for emb in self._cache.values())
        }

    def get_model_info(self) -> Dict[str, Any]:
        """Get model information"""
        return {
            'model_name': self.model_name,
            'dimension': self.dimension,
            'device': self.device,
            'normalize': self.normalize_embeddings,
            'cache_enabled': self.cache_enabled,
            'cache_size': len(self._cache) if self.cache_enabled else 0
        }


# Global instance (singleton)
_embeddings_generator: Optional[EmbeddingsGenerator] = None
_simple_embeddings_fallback = None


def get_embeddings_generator(
    model_name: str = 'base',
    force_reload: bool = False,
    use_simple_fallback: bool = True
) -> Optional[EmbeddingsGenerator]:
    """
    Get global embeddings generator instance (singleton)

    Tries sentence-transformers first, falls back to simple embeddings if unavailable.

    Args:
        model_name: Model to use
        force_reload: Force reload of model
        use_simple_fallback: Use simple embeddings as fallback (Python 3.9 compatible)

    Returns:
        EmbeddingsGenerator instance or None if not available
    """
    global _embeddings_generator, _simple_embeddings_fallback

    if _embeddings_generator is None or force_reload:
        try:
            _embeddings_generator = EmbeddingsGenerator(model_name=model_name)
        except Exception as e:
            logger.warning(f"sentence-transformers not available: {e}")

            # Try simple embeddings fallback
            if use_simple_fallback:
                try:
                    from core.simple_embeddings import get_simple_embeddings, SimpleEmbeddingsGenerator

                    # Create adapter to match EmbeddingsGenerator interface
                    class SimpleEmbeddingsAdapter:
                        def __init__(self, simple_gen):
                            self.simple_gen = simple_gen
                            self.model_name = 'simple-fallback'
                            self.dimension = simple_gen.dimension

                        def generate(self, text):
                            result = self.simple_gen.generate(text)
                            # Adapt to EmbeddingResult format
                            from dataclasses import dataclass
                            @dataclass
                            class AdaptedResult:
                                text: str
                                embedding: list
                                dimension: int
                                model: str = 'simple-fallback'

                            if isinstance(result, list):
                                return [AdaptedResult(r.text, r.embedding, r.dimension) for r in result]
                            else:
                                return AdaptedResult(result.text, result.embedding, result.dimension)

                        def similarity(self, text1, text2):
                            return self.simple_gen.similarity(text1, text2)

                    _simple_embeddings_fallback = SimpleEmbeddingsAdapter(get_simple_embeddings())
                    logger.info("✓ Using simple embeddings fallback (Python 3.9 compatible)")
                    return _simple_embeddings_fallback

                except Exception as e2:
                    logger.error(f"Failed to initialize simple embeddings fallback: {e2}")
            return None

    return _embeddings_generator


if __name__ == "__main__":
    # Test embeddings generation
    logging.basicConfig(level=logging.INFO)

    print("\n" + "="*60)
    print("Testing Embeddings Generator")
    print("="*60 + "\n")

    if not SENTENCE_TRANSFORMERS_AVAILABLE:
        print("❌ sentence-transformers not installed")
        print("Install with: pip install sentence-transformers")
        exit(1)

    # Initialize generator
    print("Loading model...")
    generator = EmbeddingsGenerator(model_name='mini')  # Use mini for faster testing

    info = generator.get_model_info()
    print(f"\n✓ Model loaded: {info['model_name']} ({info['dimension']}D)")

    # Generate embeddings
    texts = [
        "Artificial intelligence is transforming technology",
        "Machine learning models require large datasets",
        "Python is a popular programming language"
    ]

    print(f"\nGenerating embeddings for {len(texts)} texts...")
    results = generator.generate(texts)

    for i, result in enumerate(results):
        print(f"\nText {i+1}: {result.text[:50]}...")
        print(f"  Embedding dimension: {result.dimension}")
        print(f"  First 5 values: {result.embedding[:5]}")

    # Test similarity
    print("\n" + "="*60)
    print("Testing Similarity")
    print("="*60 + "\n")

    text1 = "AI and machine learning"
    text2 = "Artificial intelligence and ML"
    text3 = "The weather is nice today"

    sim12 = generator.similarity(text1, text2)
    sim13 = generator.similarity(text1, text3)

    print(f"Similarity (AI vs AI): {sim12:.4f}")
    print(f"Similarity (AI vs Weather): {sim13:.4f}")

    # Test find most similar
    print("\n" + "="*60)
    print("Testing Find Most Similar")
    print("="*60 + "\n")

    query = "deep learning"
    candidates = [
        "neural networks and deep learning",
        "machine learning algorithms",
        "cooking recipes",
        "natural language processing",
        "gardening tips"
    ]

    top_results = generator.find_most_similar(query, candidates, top_k=3)

    print(f"Query: {query}")
    print("\nTop 3 most similar:")
    for text, score in top_results:
        print(f"  {score:.4f}: {text}")

    # Cache stats
    print("\n" + "="*60)
    print("Cache Statistics")
    print("="*60 + "\n")

    cache_stats = generator.get_cache_stats()
    print(f"Cache size: {cache_stats['size']} embeddings")
    print(f"Total bytes: {cache_stats['total_bytes']:,}")

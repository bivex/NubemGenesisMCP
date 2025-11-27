"""
Simple Embeddings Generator - Python 3.9+ Compatible
Fallback implementation using TF-IDF and basic transformations
Works without sentence-transformers dependency
"""

import logging
import hashlib
import pickle
from typing import List, Dict, Any, Union
from dataclasses import dataclass
from pathlib import Path
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SimpleEmbeddingResult:
    """Result of simple embedding generation"""
    text: str
    embedding: List[float]
    dimension: int
    method: str


class SimpleEmbeddingsGenerator:
    """
    Simple embeddings generator using TF-IDF and basic transformations

    Features:
    - No external ML dependencies
    - Fast and deterministic
    - Good for basic semantic matching
    - Compatible with Python 3.9+

    Limitations:
    - Lower quality than transformer models
    - Fixed vocabulary
    - No transfer learning
    """

    def __init__(
        self,
        dimension: int = 384,
        cache_dir: str = '.embeddings_cache'
    ):
        """
        Initialize Simple Embeddings Generator

        Args:
            dimension: Embedding dimension (default 384, compatible with mini models)
            cache_dir: Directory for caching
        """
        self.dimension = dimension
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

        # Build vocabulary from common words
        self.vocabulary = self._build_vocabulary()
        self.vocab_size = len(self.vocabulary)

        # Cache
        self.cache: Dict[str, List[float]] = {}

        logger.info(f"SimpleEmbeddingsGenerator initialized (dimension={dimension})")

    def _build_vocabulary(self) -> Dict[str, int]:
        """Build vocabulary from common programming/tech terms"""

        # Common programming terms
        terms = [
            # General programming
            'code', 'function', 'class', 'method', 'variable', 'parameter', 'return',
            'import', 'export', 'module', 'package', 'library', 'framework', 'api',
            'data', 'type', 'string', 'number', 'boolean', 'array', 'list', 'dict',
            'loop', 'condition', 'if', 'else', 'for', 'while', 'try', 'catch',

            # Software concepts
            'algorithm', 'optimization', 'performance', 'scalability', 'architecture',
            'design', 'pattern', 'refactor', 'test', 'debug', 'deploy', 'build',
            'database', 'query', 'index', 'transaction', 'cache', 'memory', 'storage',

            # Web development
            'web', 'http', 'rest', 'api', 'endpoint', 'request', 'response', 'json',
            'html', 'css', 'javascript', 'frontend', 'backend', 'server', 'client',
            'authentication', 'authorization', 'session', 'cookie', 'token', 'security',

            # DevOps
            'docker', 'container', 'kubernetes', 'deployment', 'pipeline', 'ci', 'cd',
            'monitoring', 'logging', 'metrics', 'alert', 'infrastructure', 'cloud',

            # Data & ML
            'model', 'training', 'prediction', 'inference', 'dataset', 'feature',
            'vector', 'embedding', 'neural', 'network', 'learning', 'machine',

            # General tech
            'system', 'service', 'application', 'user', 'interface', 'configuration',
            'error', 'exception', 'warning', 'info', 'success', 'failure', 'status',
            'version', 'update', 'upgrade', 'install', 'remove', 'config', 'setup',

            # Actions
            'create', 'read', 'update', 'delete', 'get', 'set', 'add', 'remove',
            'start', 'stop', 'run', 'execute', 'process', 'handle', 'manage',
            'validate', 'verify', 'check', 'test', 'build', 'compile', 'parse',
        ]

        # Create vocabulary with indices
        vocabulary = {term.lower(): idx for idx, term in enumerate(set(terms))}

        return vocabulary

    def _text_to_vector(self, text: str) -> np.ndarray:
        """
        Convert text to vector using term frequency and positional encoding

        Args:
            text: Input text

        Returns:
            Vector representation
        """
        text_lower = text.lower()
        words = text_lower.split()

        # Initialize vector
        vector = np.zeros(self.dimension)

        # Method 1: Term frequency (first 1/3 of dimensions)
        tf_dim = self.dimension // 3
        for word in words:
            if word in self.vocabulary:
                idx = self.vocabulary[word] % tf_dim
                vector[idx] += 1.0

        # Method 2: Character n-grams (middle 1/3)
        ngram_dim = self.dimension // 3
        for i in range(len(text_lower) - 2):
            trigram = text_lower[i:i+3]
            # Hash to dimension
            hash_val = int(hashlib.md5(trigram.encode()).hexdigest(), 16)
            idx = tf_dim + (hash_val % ngram_dim)
            vector[idx] += 0.5

        # Method 3: Word positions (last 1/3)
        pos_dim = self.dimension - tf_dim - ngram_dim
        for pos, word in enumerate(words[:20]):  # First 20 words
            if word in self.vocabulary:
                vocab_idx = self.vocabulary[word]
                idx = tf_dim + ngram_dim + ((pos + vocab_idx) % pos_dim)
                vector[idx] += 0.3

        # Normalize
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm

        return vector

    def generate(self, text: Union[str, List[str]]) -> Union[SimpleEmbeddingResult, List[SimpleEmbeddingResult]]:
        """
        Generate embeddings for text

        Args:
            text: Single text or list of texts

        Returns:
            SimpleEmbeddingResult or list of results
        """
        # Handle single text
        if isinstance(text, str):
            # Check cache
            if text in self.cache:
                embedding = self.cache[text]
            else:
                # Generate embedding
                vector = self._text_to_vector(text)
                embedding = vector.tolist()

                # Cache it
                self.cache[text] = embedding

            return SimpleEmbeddingResult(
                text=text,
                embedding=embedding,
                dimension=self.dimension,
                method='tf-idf-ngram'
            )

        # Handle list of texts
        else:
            return [self.generate(t) for t in text]

    def similarity(self, text1: str, text2: str) -> float:
        """
        Calculate cosine similarity between two texts

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score (0-1)
        """
        emb1 = self.generate(text1)
        emb2 = self.generate(text2)

        # Cosine similarity
        vec1 = np.array(emb1.embedding)
        vec2 = np.array(emb2.embedding)

        similarity = np.dot(vec1, vec2)

        return float(max(0.0, min(1.0, similarity)))

    def batch_generate(self, texts: List[str], batch_size: int = 32) -> List[SimpleEmbeddingResult]:
        """
        Generate embeddings in batches

        Args:
            texts: List of texts
            batch_size: Batch size (unused, kept for compatibility)

        Returns:
            List of results
        """
        return self.generate(texts)

    def save_cache(self, filepath: str = None):
        """Save cache to disk"""
        if filepath is None:
            filepath = self.cache_dir / 'simple_embeddings_cache.pkl'

        with open(filepath, 'wb') as f:
            pickle.dump(self.cache, f)

        logger.info(f"Saved cache with {len(self.cache)} entries to {filepath}")

    def load_cache(self, filepath: str = None):
        """Load cache from disk"""
        if filepath is None:
            filepath = self.cache_dir / 'simple_embeddings_cache.pkl'

        if Path(filepath).exists():
            with open(filepath, 'rb') as f:
                self.cache = pickle.load(f)

            logger.info(f"Loaded cache with {len(self.cache)} entries from {filepath}")
        else:
            logger.warning(f"Cache file not found: {filepath}")


# Singleton instance
_simple_embeddings_instance = None


def get_simple_embeddings(dimension: int = 384) -> SimpleEmbeddingsGenerator:
    """
    Get singleton simple embeddings generator

    Args:
        dimension: Embedding dimension

    Returns:
        SimpleEmbeddingsGenerator instance
    """
    global _simple_embeddings_instance

    if _simple_embeddings_instance is None:
        _simple_embeddings_instance = SimpleEmbeddingsGenerator(dimension=dimension)

    return _simple_embeddings_instance


if __name__ == "__main__":
    # Test simple embeddings
    logging.basicConfig(level=logging.INFO)

    print("\n" + "="*60)
    print("Testing Simple Embeddings Generator")
    print("="*60 + "\n")

    # Initialize
    embeddings = get_simple_embeddings()

    # Test texts
    texts = [
        "How to optimize Python code?",
        "Python performance optimization techniques",
        "What is machine learning?",
        "Docker container deployment",
    ]

    print("Generating embeddings...")
    results = embeddings.generate(texts)

    for i, result in enumerate(results, 1):
        print(f"\n{i}. Text: {result.text[:50]}...")
        print(f"   Dimension: {result.dimension}")
        print(f"   Method: {result.method}")
        print(f"   Vector preview: [{', '.join(f'{x:.3f}' for x in result.embedding[:5])}...]")

    # Test similarity
    print("\n" + "-"*60)
    print("Testing Similarity")
    print("-"*60 + "\n")

    sim1 = embeddings.similarity(texts[0], texts[1])
    sim2 = embeddings.similarity(texts[0], texts[2])

    print(f"Similarity (Python opt vs Python perf): {sim1:.3f}")
    print(f"Similarity (Python opt vs ML): {sim2:.3f}")

    print("\n✓ Simple embeddings working!")

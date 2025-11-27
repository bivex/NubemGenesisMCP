# Embeddings module
from .embedding_manager import (
    EmbeddingManager,
    get_embedding_manager,
    generate_embedding,
    batch_generate_embeddings,
    calculate_similarity
)

__all__ = [
    'EmbeddingManager',
    'get_embedding_manager',
    'generate_embedding',
    'batch_generate_embeddings',
    'calculate_similarity'
]
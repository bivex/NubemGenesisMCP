"""
Vector Database Integration - Qdrant
Implementación de base de datos vectorial para RAG mejorado
"""

import os
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import hashlib

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    logging.warning("Qdrant client not installed. Install with: pip install qdrant-client")

logger = logging.getLogger(__name__)


@dataclass
class VectorSearchResult:
    """Resultado de búsqueda vectorial"""
    content: str
    score: float
    metadata: Dict[str, Any]
    id: str


class VectorDatabase:
    """
    Vector Database usando Qdrant para RAG mejorado

    Features:
    - Almacenamiento de embeddings de documentos
    - Búsqueda de similitud semántica
    - Metadata filtering
    - Gestión de colecciones
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        collection_name: str = "nubem_knowledge",
        vector_size: int = 768,
        distance: str = "cosine"
    ):
        """
        Inicializar Vector Database

        Args:
            host: Host de Qdrant
            port: Puerto de Qdrant
            collection_name: Nombre de la colección
            vector_size: Dimensión de los vectores (768 para sentence-transformers)
            distance: Métrica de distancia (cosine, euclidean, dot)
        """
        if not QDRANT_AVAILABLE:
            raise ImportError("Qdrant client not installed. Install with: pip install qdrant-client")

        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.vector_size = vector_size

        # Mapeo de distancias
        distance_map = {
            "cosine": Distance.COSINE,
            "euclidean": Distance.EUCLID,
            "dot": Distance.DOT,
        }
        self.distance = distance_map.get(distance.lower(), Distance.COSINE)

        # Inicializar cliente
        self.client: Optional[QdrantClient] = None
        self._initialize_client()

    def _initialize_client(self):
        """Inicializar cliente de Qdrant"""
        try:
            self.client = QdrantClient(host=self.host, port=self.port)

            # Verificar conexión
            collections = self.client.get_collections()
            logger.info(f"Connected to Qdrant at {self.host}:{self.port}")

            # Crear colección si no existe
            self._ensure_collection()

        except Exception as e:
            logger.warning(f"Failed to connect to Qdrant: {e}")
            logger.warning("Vector search will not be available. Start Qdrant with: docker run -p 6333:6333 qdrant/qdrant")
            self.client = None

    def _ensure_collection(self):
        """Asegurar que la colección existe"""
        if not self.client:
            return

        try:
            # Verificar si la colección existe
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]

            if self.collection_name not in collection_names:
                # Crear colección
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=self.distance
                    )
                )
                logger.info(f"Created collection: {self.collection_name}")
            else:
                logger.info(f"Collection {self.collection_name} already exists")

        except Exception as e:
            logger.error(f"Error ensuring collection: {e}")

    def add_documents(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        metadata: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        Agregar documentos a la base de datos vectorial

        Args:
            documents: Lista de textos
            embeddings: Lista de vectores de embeddings
            metadata: Metadata opcional por documento

        Returns:
            True si se agregaron exitosamente
        """
        if not self.client:
            logger.warning("Qdrant client not initialized")
            return False

        if len(documents) != len(embeddings):
            logger.error("Documents and embeddings must have same length")
            return False

        if metadata and len(metadata) != len(documents):
            logger.error("Metadata must have same length as documents")
            return False

        try:
            points = []
            for idx, (doc, emb) in enumerate(zip(documents, embeddings)):
                # Generar ID único basado en contenido
                doc_id = hashlib.md5(doc.encode()).hexdigest()

                # Preparar metadata
                doc_metadata = metadata[idx] if metadata else {}
                doc_metadata["text"] = doc

                # Crear punto
                point = PointStruct(
                    id=doc_id,
                    vector=emb,
                    payload=doc_metadata
                )
                points.append(point)

            # Insertar en Qdrant
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )

            logger.info(f"Added {len(points)} documents to {self.collection_name}")
            return True

        except Exception as e:
            logger.error(f"Error adding documents: {e}")
            return False

    def search(
        self,
        query_embedding: List[float],
        limit: int = 5,
        score_threshold: Optional[float] = None,
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[VectorSearchResult]:
        """
        Buscar documentos similares

        Args:
            query_embedding: Vector de la query
            limit: Número máximo de resultados
            score_threshold: Score mínimo (opcional)
            metadata_filter: Filtros de metadata (opcional)

        Returns:
            Lista de resultados ordenados por similitud
        """
        if not self.client:
            logger.warning("Qdrant client not initialized")
            return []

        try:
            # Preparar filtros si existen
            search_filter = None
            if metadata_filter:
                # TODO: Implementar filtros de Qdrant
                pass

            # Realizar búsqueda
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=search_filter
            )

            # Convertir a VectorSearchResult
            search_results = []
            for result in results:
                search_results.append(VectorSearchResult(
                    content=result.payload.get("text", ""),
                    score=result.score,
                    metadata={k: v for k, v in result.payload.items() if k != "text"},
                    id=result.id
                ))

            logger.info(f"Found {len(search_results)} results for query")
            return search_results

        except Exception as e:
            logger.error(f"Error searching: {e}")
            return []

    def delete_collection(self) -> bool:
        """Eliminar colección completa"""
        if not self.client:
            return False

        try:
            self.client.delete_collection(collection_name=self.collection_name)
            logger.info(f"Deleted collection: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"Error deleting collection: {e}")
            return False

    def count_documents(self) -> int:
        """Contar documentos en la colección"""
        if not self.client:
            return 0

        try:
            collection_info = self.client.get_collection(collection_name=self.collection_name)
            return collection_info.points_count
        except Exception as e:
            logger.error(f"Error counting documents: {e}")
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """Obtener estadísticas de la colección"""
        if not self.client:
            return {"available": False}

        try:
            collection_info = self.client.get_collection(collection_name=self.collection_name)
            return {
                "available": True,
                "collection_name": self.collection_name,
                "points_count": collection_info.points_count,
                "vector_size": self.vector_size,
                "distance": str(self.distance),
                "host": self.host,
                "port": self.port
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {"available": False, "error": str(e)}


# Instancia global (singleton)
_vector_db_instance: Optional[VectorDatabase] = None


def get_vector_database() -> Optional[VectorDatabase]:
    """
    Obtener instancia de Vector Database (singleton)

    Returns:
        VectorDatabase instance o None si no está disponible
    """
    global _vector_db_instance

    if _vector_db_instance is None:
        try:
            # Obtener configuración del entorno
            host = os.getenv("QDRANT_HOST", "localhost")
            port = int(os.getenv("QDRANT_PORT", "6333"))
            collection = os.getenv("QDRANT_COLLECTION", "nubem_knowledge")

            _vector_db_instance = VectorDatabase(
                host=host,
                port=port,
                collection_name=collection
            )
        except Exception as e:
            logger.error(f"Failed to initialize vector database: {e}")
            return None

    return _vector_db_instance


if __name__ == "__main__":
    # Test básico
    logging.basicConfig(level=logging.INFO)

    print("Testing Vector Database...")
    db = get_vector_database()

    if db and db.client:
        stats = db.get_stats()
        print(f"Stats: {stats}")
        print("✅ Vector Database available")
    else:
        print("❌ Vector Database not available")
        print("Start Qdrant with: docker run -p 6333:6333 qdrant/qdrant")

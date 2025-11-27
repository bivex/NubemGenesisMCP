#!/usr/bin/env python3
"""
SQLite Vector Store - Alternativa ligera a Qdrant
Usa SQLite con embeddings locales para funcionar sin Docker
"""

import os
import sqlite3
import json
import numpy as np
from typing import List, Dict, Any, Optional
from pathlib import Path
import hashlib
from datetime import datetime

class SQLiteVectorStore:
    """Vector store usando SQLite como backend"""

    def __init__(self, db_path: Optional[str] = None):
        """Inicializa el store con SQLite"""
        if db_path is None:
            db_path = os.path.expanduser("~/.nubemclaude/vectors.db")

        # Crear directorio si no existe
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        self._init_database()
        self._embedder = None

    def _init_database(self):
        """Crea las tablas necesarias"""
        cursor = self.conn.cursor()

        # Tabla principal de vectores
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vectors (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                embedding BLOB NOT NULL,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                collection TEXT DEFAULT 'default'
            )
        """)

        # Índices para búsqueda eficiente
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_collection
            ON vectors(collection)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_created_at
            ON vectors(created_at DESC)
        """)

        # Tabla de sesiones
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                messages TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.conn.commit()

    def get_embedder(self):
        """Lazy load del embedder local"""
        if self._embedder is None:
            try:
                # Intentar usar sentence-transformers (más rápido)
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer('all-MiniLM-L6-v2')
                self._embed_method = 'sentence-transformers'
            except ImportError:
                # Fallback a embeddings simples con hash
                self._embedder = self._simple_embedder
                self._embed_method = 'simple'
                print("⚠️ sentence-transformers no instalado. Usando embeddings simples.")

        return self._embedder

    def _simple_embedder(self, text: str) -> np.ndarray:
        """Embedder simple basado en hash para fallback"""
        # Crear vector de 384 dimensiones basado en hash del texto
        hash_obj = hashlib.sha384(text.encode())
        hash_bytes = hash_obj.digest()

        # Convertir a vector normalizado
        vector = np.frombuffer(hash_bytes, dtype=np.uint8).astype(np.float32)
        vector = (vector / 255.0) - 0.5  # Normalizar a [-0.5, 0.5]

        return vector

    def embed_text(self, text: str) -> np.ndarray:
        """Genera embedding para un texto"""
        embedder = self.get_embedder()

        if self._embed_method == 'sentence-transformers':
            return embedder.encode(text)
        else:
            return embedder(text)

    def add_vector(self, content: str, metadata: Optional[Dict] = None,
                  collection: str = 'default') -> str:
        """Añade un vector al store"""
        # Generar ID único
        vector_id = hashlib.md5(f"{content}{datetime.now()}".encode()).hexdigest()

        # Generar embedding
        embedding = self.embed_text(content)

        # Serializar embedding y metadata
        embedding_blob = embedding.tobytes()
        metadata_json = json.dumps(metadata) if metadata else '{}'

        # Insertar en la base de datos
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO vectors (id, content, embedding, metadata, collection)
            VALUES (?, ?, ?, ?, ?)
        """, (vector_id, content, embedding_blob, metadata_json, collection))

        self.conn.commit()
        return vector_id

    def search(self, query: str, collection: str = 'default',
              limit: int = 5) -> List[Dict[str, Any]]:
        """Busca vectores similares"""
        # Generar embedding de la query
        query_embedding = self.embed_text(query)

        # Obtener todos los vectores de la colección
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, content, embedding, metadata, created_at
            FROM vectors
            WHERE collection = ?
            ORDER BY created_at DESC
            LIMIT 1000
        """, (collection,))

        results = []
        for row in cursor.fetchall():
            # Deserializar embedding
            stored_embedding = np.frombuffer(row['embedding'], dtype=np.float32)

            # Calcular similaridad coseno
            similarity = self._cosine_similarity(query_embedding, stored_embedding)

            results.append({
                'id': row['id'],
                'content': row['content'],
                'metadata': json.loads(row['metadata']),
                'score': float(similarity),
                'created_at': row['created_at']
            })

        # Ordenar por score y limitar
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:limit]

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calcula similaridad coseno entre dos vectores"""
        # Asegurar mismas dimensiones
        if len(a) != len(b):
            # Pad o truncar si es necesario
            min_len = min(len(a), len(b))
            a = a[:min_len]
            b = b[:min_len]

        # Calcular similaridad
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    def save_session(self, session_id: str, messages: List[Dict]) -> None:
        """Guarda una sesión de chat"""
        messages_json = json.dumps(messages)

        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO sessions (session_id, messages, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (session_id, messages_json))

        self.conn.commit()

    def load_session(self, session_id: str) -> Optional[List[Dict]]:
        """Carga una sesión de chat"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT messages FROM sessions WHERE session_id = ?
        """, (session_id,))

        row = cursor.fetchone()
        if row:
            return json.loads(row['messages'])
        return None

    def list_sessions(self, limit: int = 10) -> List[Dict]:
        """Lista las sesiones recientes"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT session_id, created_at, updated_at
            FROM sessions
            ORDER BY updated_at DESC
            LIMIT ?
        """, (limit,))

        sessions = []
        for row in cursor.fetchall():
            sessions.append({
                'session_id': row['session_id'],
                'created_at': row['created_at'],
                'updated_at': row['updated_at']
            })

        return sessions

    def clear_collection(self, collection: str = 'default') -> int:
        """Limpia una colección"""
        cursor = self.conn.cursor()
        cursor.execute("""
            DELETE FROM vectors WHERE collection = ?
        """, (collection,))

        deleted = cursor.rowcount
        self.conn.commit()
        return deleted

    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del store"""
        cursor = self.conn.cursor()

        # Total de vectores
        cursor.execute("SELECT COUNT(*) as total FROM vectors")
        total_vectors = cursor.fetchone()['total']

        # Vectores por colección
        cursor.execute("""
            SELECT collection, COUNT(*) as count
            FROM vectors
            GROUP BY collection
        """)
        collections = {row['collection']: row['count'] for row in cursor.fetchall()}

        # Total de sesiones
        cursor.execute("SELECT COUNT(*) as total FROM sessions")
        total_sessions = cursor.fetchone()['total']

        # Tamaño de la base de datos
        db_size = os.path.getsize(self.db_path) / (1024 * 1024)  # En MB

        return {
            'total_vectors': total_vectors,
            'collections': collections,
            'total_sessions': total_sessions,
            'db_size_mb': round(db_size, 2),
            'embed_method': self._embed_method if self._embedder else 'not_initialized'
        }

    def close(self):
        """Cierra la conexión"""
        if self.conn:
            self.conn.close()


# Wrapper compatible con Qdrant API
class SQLiteQdrantCompat(SQLiteVectorStore):
    """Wrapper para compatibilidad con API de Qdrant"""

    def upsert(self, collection_name: str, points: List[Dict]) -> None:
        """Emula upsert de Qdrant"""
        for point in points:
            content = point.get('payload', {}).get('content', '')
            metadata = point.get('payload', {})
            self.add_vector(content, metadata, collection_name)

    def search_points(self, collection_name: str, query_vector: Any,
                     limit: int = 5) -> List[Dict]:
        """Emula search de Qdrant"""
        # Si query_vector es string, buscar directamente
        if isinstance(query_vector, str):
            return self.search(query_vector, collection_name, limit)

        # Si es vector, necesitaríamos el contenido original
        # Por ahora, retornar vacío
        return []


# Testing
if __name__ == "__main__":
    print("🧪 Testing SQLite Vector Store...")

    # Crear store
    store = SQLiteVectorStore()

    # Añadir algunos vectores
    store.add_vector("Python es un lenguaje de programación", {'type': 'programming'})
    store.add_vector("JavaScript es usado para desarrollo web", {'type': 'programming'})
    store.add_vector("El cielo es azul", {'type': 'general'})

    # Buscar
    results = store.search("lenguajes de programación", limit=2)

    print("\n📊 Resultados de búsqueda:")
    for r in results:
        print(f"  - [{r['score']:.3f}] {r['content'][:50]}...")

    # Stats
    stats = store.get_stats()
    print(f"\n📈 Estadísticas:")
    print(f"  Total vectores: {stats['total_vectors']}")
    print(f"  Tamaño DB: {stats['db_size_mb']} MB")
    print(f"  Método embedding: {stats['embed_method']}")

    store.close()
    print("\n✅ Test completado!")
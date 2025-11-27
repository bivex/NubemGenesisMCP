#!/usr/bin/env python3
"""
Claude Context Manager - Sistema de gestión de contexto ampliado
Permite persistir y recuperar contexto entre sesiones usando vectores
"""

import json
import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging
from dataclasses import dataclass, asdict

from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from qdrant_client.models import Filter, FieldCondition, MatchValue

logger = logging.getLogger(__name__)


@dataclass
class ConversationMessage:
    """Representa un mensaje en la conversación"""
    content: str
    role: str  # "user" or "assistant"
    timestamp: str
    session_id: str
    terminal_id: str
    relevance_score: float = 0.0
    
    def to_dict(self):
        return asdict(self)


class ClaudeContextManager:
    """Gestiona contexto ampliado para Claude usando vectores"""
    
    def __init__(self, 
                 qdrant_host: str = "localhost",
                 qdrant_port: int = 6333,
                 max_context_tokens: int = 100000):
        
        self.qdrant = QdrantClient(host=qdrant_host, port=qdrant_port)
        self.collection = "claude_context"
        self.sessions_collection = "claude_sessions"
        self.max_context_tokens = max_context_tokens
        self.embedding_dim = 384
        
        # Directorio para cache local
        self.cache_dir = Path.home() / ".claude_context_cache"
        self.cache_dir.mkdir(exist_ok=True)
        
        # Inicializar colecciones
        self._init_collections()
        
        # Cargar modelo de embeddings si está disponible
        self.embedding_model = self._load_embedding_model()
    
    def _init_collections(self):
        """Inicializa colecciones en Qdrant"""
        try:
            # Colección para mensajes individuales
            collections = self.qdrant.get_collections()
            existing = [col.name for col in collections.collections]
            
            if self.collection not in existing:
                self.qdrant.create_collection(
                    collection_name=self.collection,
                    vectors_config=VectorParams(
                        size=self.embedding_dim,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created collection: {self.collection}")
            
            # Colección para resúmenes de sesiones
            if self.sessions_collection not in existing:
                self.qdrant.create_collection(
                    collection_name=self.sessions_collection,
                    vectors_config=VectorParams(
                        size=self.embedding_dim,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created collection: {self.sessions_collection}")
                
        except Exception as e:
            logger.error(f"Error initializing collections: {e}")
            self.qdrant = None
    
    def _load_embedding_model(self):
        """Carga modelo de embeddings"""
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("Embedding model loaded for context management")
            return model
        except:
            logger.warning("Using hash-based embeddings for context")
            return None
    
    def create_embedding(self, text: str) -> List[float]:
        """Crea embedding de un texto"""
        if self.embedding_model:
            try:
                embedding = self.embedding_model.encode(text, show_progress_bar=False)
                return embedding.tolist()
            except Exception as e:
                logger.error(f"Error creating embedding: {e}")
        
        # Fallback: hash-based embedding
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        import random
        random.seed(text_hash)
        vector = [random.gauss(0, 1) for _ in range(self.embedding_dim)]
        norm = sum(x**2 for x in vector) ** 0.5
        if norm > 0:
            vector = [x / norm for x in vector]
        return vector
    
    def capture_message(self, 
                       message: str, 
                       role: str = "user",
                       session_id: Optional[str] = None,
                       metadata: Optional[Dict] = None) -> str:
        """
        Captura un mensaje de la conversación y lo guarda como vector
        
        Args:
            message: Contenido del mensaje
            role: "user" o "assistant"
            session_id: ID de la sesión (se genera si no se proporciona)
            metadata: Metadata adicional
            
        Returns:
            session_id usado
        """
        
        if not session_id:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        terminal_id = os.environ.get("TERM_SESSION_ID", 
                                     os.environ.get("TERM", "unknown"))
        
        # Crear embedding
        vector = self.create_embedding(message)
        
        # Preparar metadata
        payload = {
            "message": message[:10000],  # Limitar tamaño
            "role": role,
            "session_id": session_id,
            "terminal_id": terminal_id,
            "timestamp": datetime.now().isoformat(),
            "length": len(message),
            "working_dir": os.getcwd()
        }
        
        if metadata:
            payload.update(metadata)
        
        # Guardar en Qdrant
        if self.qdrant:
            try:
                point_id = abs(hash(f"{session_id}_{datetime.now().isoformat()}_{role}")) % (10 ** 8)
                
                self.qdrant.upsert(
                    collection_name=self.collection,
                    points=[PointStruct(
                        id=point_id,
                        vector=vector,
                        payload=payload
                    )]
                )
                logger.info(f"Captured {role} message for session {session_id}")
            except Exception as e:
                logger.error(f"Error saving to Qdrant: {e}")
        
        # También guardar en cache local
        self._save_to_local_cache(session_id, message, role)
        
        return session_id
    
    def get_relevant_context(self, 
                           query: str,
                           session_id: Optional[str] = None,
                           limit: int = 10,
                           include_all_sessions: bool = False) -> List[ConversationMessage]:
        """
        Recupera contexto relevante para una query
        
        Args:
            query: Texto de búsqueda
            session_id: Filtrar por sesión específica
            limit: Número máximo de resultados
            include_all_sessions: Si incluir todas las sesiones
            
        Returns:
            Lista de mensajes relevantes
        """
        
        if not self.qdrant:
            return self._get_local_context(query, session_id, limit)
        
        # Crear embedding de la query
        query_vector = self.create_embedding(query)
        
        # Preparar filtros
        filters = None
        if session_id and not include_all_sessions:
            filters = Filter(
                must=[
                    FieldCondition(
                        key="session_id",
                        match=MatchValue(value=session_id)
                    )
                ]
            )
        
        # Buscar en Qdrant
        try:
            results = self.qdrant.search(
                collection_name=self.collection,
                query_vector=query_vector,
                query_filter=filters,
                limit=limit,
                with_payload=True
            )
            
            # Convertir a ConversationMessage
            messages = []
            for result in results:
                msg = ConversationMessage(
                    content=result.payload.get("message", ""),
                    role=result.payload.get("role", "unknown"),
                    timestamp=result.payload.get("timestamp", ""),
                    session_id=result.payload.get("session_id", ""),
                    terminal_id=result.payload.get("terminal_id", ""),
                    relevance_score=result.score
                )
                messages.append(msg)
            
            return messages
            
        except Exception as e:
            logger.error(f"Error searching context: {e}")
            return []
    
    def get_session_history(self, 
                          session_id: str,
                          limit: int = 50) -> List[ConversationMessage]:
        """
        Obtiene el historial completo de una sesión
        
        Args:
            session_id: ID de la sesión
            limit: Número máximo de mensajes
            
        Returns:
            Lista de mensajes ordenados cronológicamente
        """
        
        if not self.qdrant:
            return []
        
        # Filtrar por session_id
        filters = Filter(
            must=[
                FieldCondition(
                    key="session_id",
                    match=MatchValue(value=session_id)
                )
            ]
        )
        
        # Recuperar todos los mensajes de la sesión
        try:
            # Usar scroll para obtener todos los resultados
            results, _ = self.qdrant.scroll(
                collection_name=self.collection,
                scroll_filter=filters,
                limit=limit,
                with_payload=True
            )
            
            # Convertir y ordenar por timestamp
            messages = []
            for point in results:
                msg = ConversationMessage(
                    content=point.payload.get("message", ""),
                    role=point.payload.get("role", "unknown"),
                    timestamp=point.payload.get("timestamp", ""),
                    session_id=point.payload.get("session_id", ""),
                    terminal_id=point.payload.get("terminal_id", "")
                )
                messages.append(msg)
            
            # Ordenar por timestamp
            messages.sort(key=lambda x: x.timestamp)
            
            return messages
            
        except Exception as e:
            logger.error(f"Error getting session history: {e}")
            return []
    
    def summarize_session(self, session_id: str) -> Dict[str, Any]:
        """
        Crea un resumen de una sesión
        
        Args:
            session_id: ID de la sesión a resumir
            
        Returns:
            Resumen de la sesión
        """
        
        # Obtener historial
        history = self.get_session_history(session_id)
        
        if not history:
            return {"error": "No history found for session"}
        
        # Estadísticas básicas
        total_messages = len(history)
        user_messages = [m for m in history if m.role == "user"]
        assistant_messages = [m for m in history if m.role == "assistant"]
        
        # Extraer temas principales (simplificado)
        all_content = " ".join([m.content for m in history])
        
        # Palabras más frecuentes (excluyendo comunes)
        import re
        from collections import Counter
        
        words = re.findall(r'\b[a-z]+\b', all_content.lower())
        common_words = {'the', 'is', 'at', 'which', 'on', 'a', 'an', 'as', 
                       'are', 'was', 'were', 'in', 'to', 'for', 'of', 'and'}
        filtered_words = [w for w in words if w not in common_words and len(w) > 3]
        word_freq = Counter(filtered_words).most_common(10)
        
        # Crear resumen
        summary = {
            "session_id": session_id,
            "total_messages": total_messages,
            "user_messages": len(user_messages),
            "assistant_messages": len(assistant_messages),
            "start_time": history[0].timestamp if history else None,
            "end_time": history[-1].timestamp if history else None,
            "key_topics": [word for word, _ in word_freq],
            "terminals_used": list(set(m.terminal_id for m in history))
        }
        
        # Guardar resumen como vector para búsqueda futura
        if self.qdrant:
            summary_text = f"Session {session_id}: Topics: {', '.join(summary['key_topics'])}"
            summary_vector = self.create_embedding(summary_text)
            
            try:
                self.qdrant.upsert(
                    collection_name=self.sessions_collection,
                    points=[PointStruct(
                        id=abs(hash(session_id)) % (10 ** 8),
                        vector=summary_vector,
                        payload=summary
                    )]
                )
            except Exception as e:
                logger.error(f"Error saving session summary: {e}")
        
        return summary
    
    def merge_contexts(self, 
                      session_ids: List[str],
                      query: Optional[str] = None,
                      limit: int = 20) -> List[ConversationMessage]:
        """
        Combina contextos de múltiples sesiones
        
        Args:
            session_ids: Lista de IDs de sesión
            query: Query opcional para filtrar
            limit: Límite de mensajes
            
        Returns:
            Mensajes combinados y deduplicados
        """
        
        all_messages = []
        
        for session_id in session_ids:
            if query:
                messages = self.get_relevant_context(query, session_id, limit=limit//len(session_ids))
            else:
                messages = self.get_session_history(session_id, limit=limit//len(session_ids))
            
            all_messages.extend(messages)
        
        # Deduplicar por contenido
        seen = set()
        unique_messages = []
        
        for msg in all_messages:
            msg_hash = hash(msg.content[:100])  # Hash de los primeros 100 chars
            if msg_hash not in seen:
                seen.add(msg_hash)
                unique_messages.append(msg)
        
        # Ordenar por relevancia si hay query, sino por timestamp
        if query:
            unique_messages.sort(key=lambda x: x.relevance_score, reverse=True)
        else:
            unique_messages.sort(key=lambda x: x.timestamp)
        
        return unique_messages[:limit]
    
    def _save_to_local_cache(self, session_id: str, message: str, role: str):
        """Guarda mensaje en cache local como backup"""
        cache_file = self.cache_dir / f"session_{session_id}.jsonl"
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "role": role,
            "message": message,
            "session_id": session_id
        }
        
        try:
            with open(cache_file, 'a') as f:
                f.write(json.dumps(entry) + '\n')
        except Exception as e:
            logger.error(f"Error saving to local cache: {e}")
    
    def _get_local_context(self, query: str, session_id: str, limit: int) -> List[ConversationMessage]:
        """Recupera contexto del cache local cuando Qdrant no está disponible"""
        messages = []
        
        # Buscar archivos de sesión
        if session_id:
            cache_files = [self.cache_dir / f"session_{session_id}.jsonl"]
        else:
            cache_files = list(self.cache_dir.glob("session_*.jsonl"))
        
        for cache_file in cache_files:
            if cache_file.exists():
                try:
                    with open(cache_file, 'r') as f:
                        for line in f:
                            entry = json.loads(line)
                            msg = ConversationMessage(
                                content=entry['message'],
                                role=entry['role'],
                                timestamp=entry['timestamp'],
                                session_id=entry['session_id'],
                                terminal_id="cached"
                            )
                            messages.append(msg)
                except Exception as e:
                    logger.error(f"Error reading cache file {cache_file}: {e}")
        
        # Filtrar por query si se proporciona (búsqueda simple)
        if query:
            query_lower = query.lower()
            messages = [m for m in messages if query_lower in m.content.lower()]
        
        return messages[:limit]
    
    def export_session(self, session_id: str, format: str = "markdown") -> str:
        """
        Exporta una sesión a formato legible
        
        Args:
            session_id: ID de la sesión
            format: "markdown" o "json"
            
        Returns:
            Sesión exportada como string
        """
        
        history = self.get_session_history(session_id)
        
        if format == "markdown":
            output = f"# Claude Session: {session_id}\n\n"
            
            for msg in history:
                timestamp = msg.timestamp.split('T')[0] if 'T' in msg.timestamp else msg.timestamp
                role_emoji = "👤" if msg.role == "user" else "🤖"
                output += f"## {role_emoji} {msg.role.title()} - {timestamp}\n\n"
                output += f"{msg.content}\n\n"
                output += "---\n\n"
            
            return output
            
        elif format == "json":
            return json.dumps([msg.to_dict() for msg in history], indent=2)
        
        else:
            return str(history)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Obtiene estadísticas del sistema de contexto"""
        
        stats = {
            "total_messages": 0,
            "total_sessions": 0,
            "cache_size_mb": 0,
            "qdrant_status": "connected" if self.qdrant else "disconnected"
        }
        
        # Contar mensajes en Qdrant
        if self.qdrant:
            try:
                collection_info = self.qdrant.get_collection(self.collection)
                stats["total_messages"] = collection_info.points_count or 0
                
                sessions_info = self.qdrant.get_collection(self.sessions_collection)
                stats["total_sessions"] = sessions_info.points_count or 0
            except:
                pass
        
        # Tamaño del cache local
        cache_size = sum(f.stat().st_size for f in self.cache_dir.glob("*.jsonl"))
        stats["cache_size_mb"] = round(cache_size / (1024 * 1024), 2)
        
        return stats


# Singleton instance
_context_manager = None

def get_context_manager() -> ClaudeContextManager:
    """Obtiene instancia singleton del gestor de contexto"""
    global _context_manager
    if _context_manager is None:
        _context_manager = ClaudeContextManager()
    return _context_manager
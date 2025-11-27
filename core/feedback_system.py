#!/usr/bin/env python3
"""
NubemSuperFClaude - Feedback System for Continuous Learning
Sistema de feedback para mejorar embeddings y selección de personas
"""

import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
import asyncio

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

logger = logging.getLogger(__name__)


@dataclass
class TaskFeedback:
    """Feedback de una tarea ejecutada"""
    task_id: str
    task_description: str
    persona_used: str
    success_score: float  # 0.0 to 1.0
    execution_time_ms: float
    user_rating: Optional[int] = None  # 1-5 stars
    comments: Optional[str] = None
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class PersonaPerformance:
    """Métricas de performance de una persona"""
    persona_id: str
    total_tasks: int
    success_rate: float
    average_execution_time: float
    average_user_rating: float
    domain_scores: Dict[str, float]  # Score por dominio
    recent_trend: str  # "improving", "stable", "declining"


class FeedbackSystem:
    """Sistema de feedback para aprendizaje continuo"""
    
    def __init__(self,
                 qdrant_host: str = "localhost",
                 qdrant_port: int = 6333,
                 feedback_file: str = "feedback_history.json"):
        
        self.qdrant = QdrantClient(host=qdrant_host, port=qdrant_port)
        self.feedback_collection = "persona_feedback"
        self.feedback_file = Path(feedback_file)
        self.feedback_history = self._load_feedback_history()
        
        # Inicializar colección de feedback en Qdrant
        self._init_feedback_collection()
    
    def _init_feedback_collection(self):
        """Inicializa colección de feedback en Qdrant"""
        try:
            collections = self.qdrant.get_collections()
            exists = any(
                col.name == self.feedback_collection 
                for col in collections.collections
            )
            
            if not exists:
                from qdrant_client.models import Distance, VectorParams
                
                self.qdrant.create_collection(
                    collection_name=self.feedback_collection,
                    vectors_config=VectorParams(
                        size=384,  # Same as persona embeddings
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created feedback collection: {self.feedback_collection}")
                
        except Exception as e:
            logger.error(f"Could not initialize feedback collection: {e}")
            self.qdrant = None
    
    def _load_feedback_history(self) -> List[TaskFeedback]:
        """Carga historial de feedback desde archivo"""
        if self.feedback_file.exists():
            try:
                with open(self.feedback_file, 'r') as f:
                    data = json.load(f)
                    return [TaskFeedback(**item) for item in data]
            except Exception as e:
                logger.error(f"Error loading feedback history: {e}")
        
        return []
    
    def _save_feedback_history(self):
        """Guarda historial de feedback a archivo"""
        try:
            data = [asdict(fb) for fb in self.feedback_history[-1000:]]  # Keep last 1000
            with open(self.feedback_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving feedback history: {e}")
    
    async def record_task_feedback(self, feedback: TaskFeedback) -> bool:
        """
        Registra feedback de una tarea ejecutada
        
        Args:
            feedback: Información de feedback de la tarea
            
        Returns:
            True si se registró exitosamente
        """
        
        # Agregar a historial
        self.feedback_history.append(feedback)
        self._save_feedback_history()
        
        # Actualizar embeddings si Qdrant está disponible
        if self.qdrant:
            await self._update_persona_embedding(feedback)
        
        # Actualizar métricas
        await self._update_performance_metrics(feedback)
        
        logger.info(f"Recorded feedback for task {feedback.task_id}")
        return True
    
    async def _update_persona_embedding(self, feedback: TaskFeedback):
        """Actualiza embedding de persona basado en feedback"""
        
        if not self.qdrant:
            return
        
        try:
            # Crear embedding del feedback
            feedback_text = f"{feedback.task_description} | Success: {feedback.success_score}"
            
            # Crear embedding simple (en producción usar modelo real)
            import hashlib
            import random
            
            text_hash = hashlib.sha256(feedback_text.encode()).hexdigest()
            random.seed(text_hash)
            feedback_vector = [random.gauss(0, 1) for _ in range(384)]
            
            # Normalizar
            norm = sum(x**2 for x in feedback_vector) ** 0.5
            if norm > 0:
                feedback_vector = [x / norm for x in feedback_vector]
            
            # Guardar en Qdrant con metadata
            point = PointStruct(
                id=abs(hash(feedback.task_id)) % (10 ** 8),
                vector=feedback_vector,
                payload={
                    'task_id': feedback.task_id,
                    'persona_id': feedback.persona_used,
                    'success_score': feedback.success_score,
                    'timestamp': feedback.timestamp,
                    'user_rating': feedback.user_rating
                }
            )
            
            self.qdrant.upsert(
                collection_name=self.feedback_collection,
                points=[point]
            )
            
        except Exception as e:
            logger.error(f"Error updating persona embedding: {e}")
    
    async def _update_performance_metrics(self, feedback: TaskFeedback):
        """Actualiza métricas de performance"""
        
        # Calcular métricas para la persona
        persona_feedback = [
            fb for fb in self.feedback_history
            if fb.persona_used == feedback.persona_used
        ]
        
        if len(persona_feedback) >= 5:  # Mínimo 5 tareas para ajustar
            # Si el performance es consistentemente bajo, marcar para revisión
            recent_scores = [fb.success_score for fb in persona_feedback[-5:]]
            avg_recent = sum(recent_scores) / len(recent_scores)
            
            if avg_recent < 0.5:
                logger.warning(
                    f"Persona {feedback.persona_used} showing poor performance: {avg_recent:.2f}"
                )
    
    def get_persona_performance(self, persona_id: str) -> PersonaPerformance:
        """
        Obtiene métricas de performance de una persona
        
        Args:
            persona_id: ID de la persona
            
        Returns:
            PersonaPerformance con métricas
        """
        
        # Filtrar feedback de esta persona
        persona_feedback = [
            fb for fb in self.feedback_history
            if fb.persona_used == persona_id
        ]
        
        if not persona_feedback:
            return PersonaPerformance(
                persona_id=persona_id,
                total_tasks=0,
                success_rate=0.0,
                average_execution_time=0.0,
                average_user_rating=0.0,
                domain_scores={},
                recent_trend="no_data"
            )
        
        # Calcular métricas
        total_tasks = len(persona_feedback)
        success_rate = sum(fb.success_score for fb in persona_feedback) / total_tasks
        avg_time = sum(fb.execution_time_ms for fb in persona_feedback) / total_tasks
        
        # Rating promedio
        rated_feedback = [fb for fb in persona_feedback if fb.user_rating]
        avg_rating = (
            sum(fb.user_rating for fb in rated_feedback) / len(rated_feedback)
            if rated_feedback else 0.0
        )
        
        # Tendencia reciente
        if total_tasks >= 10:
            old_avg = sum(fb.success_score for fb in persona_feedback[:5]) / 5
            new_avg = sum(fb.success_score for fb in persona_feedback[-5:]) / 5
            
            if new_avg > old_avg + 0.1:
                trend = "improving"
            elif new_avg < old_avg - 0.1:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"
        
        return PersonaPerformance(
            persona_id=persona_id,
            total_tasks=total_tasks,
            success_rate=success_rate,
            average_execution_time=avg_time,
            average_user_rating=avg_rating,
            domain_scores=self._calculate_domain_scores(persona_id),
            recent_trend=trend
        )
    
    def _calculate_domain_scores(self, persona_id: str) -> Dict[str, float]:
        """Calcula los puntajes por dominio para una persona"""
        domain_scores = {}
        feedbacks = [f for f in self.feedback_history if f.persona_id == persona_id]
        
        # Agrupar por tipo de tarea/dominio
        domains = set()
        for feedback in feedbacks:
            if hasattr(feedback, 'task_type'):
                domains.add(feedback.task_type)
        
        for domain in domains:
            domain_feedbacks = [f for f in feedbacks if hasattr(f, 'task_type') and f.task_type == domain]
            if domain_feedbacks:
                avg_score = sum(f.rating for f in domain_feedbacks) / len(domain_feedbacks)
                domain_scores[domain] = round(avg_score, 2)
        
        # Si no hay dominios específicos, usar categorías genéricas
        if not domain_scores:
            domain_scores = {
                "general": round(sum(f.rating for f in feedbacks) / len(feedbacks), 2) if feedbacks else 0.0,
                "speed": round(sum(1 for f in feedbacks if f.execution_time < 1.0) / max(len(feedbacks), 1) * 5, 2),
                "quality": round(sum(f.rating for f in feedbacks if f.rating >= 4) / max(len(feedbacks), 1) * 5, 2)
            }
        
        return domain_scores
    
    def get_recommended_improvements(self) -> List[Dict[str, Any]]:
        """
        Obtiene recomendaciones de mejora basadas en feedback
        
        Returns:
            Lista de recomendaciones
        """
        
        recommendations = []
        
        # Analizar personas con bajo performance
        persona_performances = {}
        for fb in self.feedback_history:
            if fb.persona_used not in persona_performances:
                persona_performances[fb.persona_used] = []
            persona_performances[fb.persona_used].append(fb.success_score)
        
        for persona_id, scores in persona_performances.items():
            if len(scores) >= 5:
                avg_score = sum(scores) / len(scores)
                
                if avg_score < 0.6:
                    recommendations.append({
                        'type': 'low_performance',
                        'persona_id': persona_id,
                        'average_score': avg_score,
                        'recommendation': f"Review and retrain {persona_id} - low success rate",
                        'priority': 'high' if avg_score < 0.4 else 'medium'
                    })
        
        # Identificar tareas problemáticas
        task_types = {}
        for fb in self.feedback_history:
            # Extraer tipo de tarea (simplificado)
            task_type = self._extract_task_type(fb.task_description)
            if task_type not in task_types:
                task_types[task_type] = []
            task_types[task_type].append(fb.success_score)
        
        for task_type, scores in task_types.items():
            if len(scores) >= 3:
                avg_score = sum(scores) / len(scores)
                
                if avg_score < 0.5:
                    recommendations.append({
                        'type': 'difficult_task_type',
                        'task_type': task_type,
                        'average_score': avg_score,
                        'recommendation': f"Need better personas for {task_type} tasks",
                        'priority': 'medium'
                    })
        
        return recommendations
    
    def _extract_task_type(self, description: str) -> str:
        """Extrae tipo de tarea de la descripción"""
        
        # Palabras clave por tipo
        task_keywords = {
            'api': ['api', 'rest', 'graphql', 'endpoint'],
            'frontend': ['ui', 'react', 'vue', 'component', 'css'],
            'backend': ['server', 'database', 'query', 'backend'],
            'security': ['security', 'auth', 'vulnerability', 'audit'],
            'performance': ['optimize', 'performance', 'speed', 'cache'],
            'testing': ['test', 'qa', 'quality', 'coverage'],
            'deployment': ['deploy', 'ci/cd', 'pipeline', 'docker']
        }
        
        description_lower = description.lower()
        
        for task_type, keywords in task_keywords.items():
            if any(keyword in description_lower for keyword in keywords):
                return task_type
        
        return 'general'
    
    async def apply_feedback_learning(self):
        """
        Aplica aprendizaje basado en feedback acumulado
        Actualiza pesos y preferencias
        """
        
        if len(self.feedback_history) < 20:
            logger.info("Not enough feedback for learning (need 20+)")
            return
        
        # Calcular ajustes por persona
        adjustments = {}
        
        for persona_id in set(fb.persona_used for fb in self.feedback_history):
            performance = self.get_persona_performance(persona_id)
            
            # Determinar ajuste
            if performance.recent_trend == "improving":
                adjustments[persona_id] = {
                    'action': 'boost',
                    'factor': 1.1,
                    'reason': 'Performance improving'
                }
            elif performance.recent_trend == "declining" and performance.success_rate < 0.5:
                adjustments[persona_id] = {
                    'action': 'reduce',
                    'factor': 0.9,
                    'reason': 'Performance declining'
                }
        
        # Aplicar ajustes (en producción esto actualizaría los embeddings)
        for persona_id, adjustment in adjustments.items():
            logger.info(
                f"Adjusting {persona_id}: {adjustment['action']} "
                f"(factor: {adjustment['factor']}, reason: {adjustment['reason']})"
            )
        
        return adjustments
    
    def export_analytics(self) -> Dict[str, Any]:
        """
        Exporta analíticas completas del sistema de feedback
        
        Returns:
            Diccionario con todas las analíticas
        """
        
        total_feedback = len(self.feedback_history)
        
        if total_feedback == 0:
            return {'message': 'No feedback data available'}
        
        # Calcular métricas globales
        overall_success = sum(fb.success_score for fb in self.feedback_history) / total_feedback
        avg_execution_time = sum(fb.execution_time_ms for fb in self.feedback_history) / total_feedback
        
        # Feedback con rating
        rated = [fb for fb in self.feedback_history if fb.user_rating]
        avg_user_rating = sum(fb.user_rating for fb in rated) / len(rated) if rated else 0
        
        # Top performing personas
        persona_scores = {}
        for fb in self.feedback_history:
            if fb.persona_used not in persona_scores:
                persona_scores[fb.persona_used] = []
            persona_scores[fb.persona_used].append(fb.success_score)
        
        top_performers = sorted(
            [
                {
                    'persona_id': pid,
                    'average_score': sum(scores) / len(scores),
                    'task_count': len(scores)
                }
                for pid, scores in persona_scores.items()
            ],
            key=lambda x: x['average_score'],
            reverse=True
        )[:5]
        
        return {
            'total_feedback_records': total_feedback,
            'overall_success_rate': round(overall_success, 3),
            'average_execution_time_ms': round(avg_execution_time, 1),
            'average_user_rating': round(avg_user_rating, 2),
            'top_performers': top_performers,
            'recommendations': self.get_recommended_improvements(),
            'last_updated': datetime.now().isoformat()
        }


# Singleton instance
_feedback_system = None

def get_feedback_system() -> FeedbackSystem:
    """Obtiene instancia singleton del sistema de feedback"""
    global _feedback_system
    if _feedback_system is None:
        _feedback_system = FeedbackSystem()
    return _feedback_system
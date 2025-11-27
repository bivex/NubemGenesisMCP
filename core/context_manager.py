"""
Context Window Management
Sistema de gestión de ventana de contexto para optimización de tokens
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import tiktoken

logger = logging.getLogger(__name__)


class ContextStrategy(Enum):
    """Estrategias de gestión de contexto"""
    SLIDING_WINDOW = "sliding_window"  # Ventana deslizante
    TRUNCATE_MIDDLE = "truncate_middle"  # Truncar del medio
    SUMMARIZE_OLD = "summarize_old"  # Resumir mensajes antiguos
    PRIORITY_BASED = "priority_based"  # Basado en prioridad


@dataclass
class Message:
    """Mensaje con metadata"""
    role: str
    content: str
    priority: int = 0  # Mayor = más importante
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ContextStats:
    """Estadísticas de contexto"""
    total_messages: int
    total_tokens: int
    system_tokens: int
    user_tokens: int
    assistant_tokens: int
    tokens_available: int
    utilization_percent: float


class ContextWindowManager:
    """
    Gestor de ventana de contexto para LLMs

    Features:
    - Conteo preciso de tokens
    - Múltiples estrategias de optimización
    - Preservación de mensajes importantes
    - Métricas de utilización
    - Soporte para múltiples modelos
    """

    # Límites de contexto por modelo
    MODEL_LIMITS = {
        # Anthropic Claude
        "claude-3-opus-20240229": 200000,
        "claude-3-sonnet-20240229": 200000,
        "claude-3-haiku-20240307": 200000,
        "claude-sonnet-4-5-20250929": 200000,

        # OpenAI GPT
        "gpt-4": 8192,
        "gpt-4-32k": 32768,
        "gpt-4-turbo": 128000,
        "gpt-4-turbo-preview": 128000,
        "gpt-3.5-turbo": 16385,
        "gpt-3.5-turbo-16k": 16385,

        # Otros
        "default": 4096
    }

    def __init__(
        self,
        model: str = "claude-sonnet-4-5-20250929",
        max_tokens: Optional[int] = None,
        buffer_ratio: float = 0.8,
        strategy: ContextStrategy = ContextStrategy.SLIDING_WINDOW,
        encoding_name: str = "cl100k_base"
    ):
        """
        Inicializar Context Window Manager

        Args:
            model: Modelo a usar (para límites de contexto)
            max_tokens: Límite máximo de tokens (None = usar límite del modelo)
            buffer_ratio: Ratio del límite a usar (0.8 = 80%)
            strategy: Estrategia de optimización
            encoding_name: Nombre del encoding de tiktoken
        """
        self.model = model
        self.strategy = strategy
        self.buffer_ratio = buffer_ratio

        # Determinar límite de tokens
        model_limit = self.MODEL_LIMITS.get(model, self.MODEL_LIMITS["default"])
        self.max_tokens = max_tokens or int(model_limit * buffer_ratio)

        # Inicializar encoder
        try:
            self.encoder = tiktoken.get_encoding(encoding_name)
        except Exception as e:
            logger.warning(f"Failed to load tiktoken encoder: {e}")
            self.encoder = None

        logger.info(f"ContextWindowManager initialized: model={model}, max_tokens={self.max_tokens}, strategy={strategy}")

    def count_tokens(self, text: str) -> int:
        """
        Contar tokens en un texto

        Args:
            text: Texto a contar

        Returns:
            Número de tokens
        """
        if not self.encoder:
            # Aproximación: ~4 caracteres por token
            return len(text) // 4

        try:
            return len(self.encoder.encode(text))
        except Exception as e:
            logger.error(f"Error counting tokens: {e}")
            return len(text) // 4

    def count_messages_tokens(self, messages: List[Dict[str, str]]) -> int:
        """
        Contar tokens en una lista de mensajes

        Args:
            messages: Lista de mensajes

        Returns:
            Total de tokens
        """
        total = 0

        for message in messages:
            # Overhead por mensaje (role + estructura)
            total += 4  # Aproximación

            # Contenido
            role = message.get("role", "")
            content = message.get("content", "")

            total += self.count_tokens(role)
            total += self.count_tokens(content)

        # Overhead final
        total += 2

        return total

    def optimize_context(
        self,
        messages: List[Dict[str, str]],
        system_message: Optional[str] = None,
        reserved_tokens: int = 1000
    ) -> Tuple[List[Dict[str, str]], ContextStats]:
        """
        Optimizar contexto según estrategia

        Args:
            messages: Lista de mensajes
            system_message: Mensaje de sistema (siempre preservado)
            reserved_tokens: Tokens reservados para respuesta

        Returns:
            Tupla de (mensajes_optimizados, estadísticas)
        """
        # Calcular tokens disponibles
        available_tokens = self.max_tokens - reserved_tokens

        if system_message:
            system_tokens = self.count_tokens(system_message)
            available_tokens -= system_tokens
        else:
            system_tokens = 0

        # Aplicar estrategia
        if self.strategy == ContextStrategy.SLIDING_WINDOW:
            optimized = self._sliding_window(messages, available_tokens)
        elif self.strategy == ContextStrategy.TRUNCATE_MIDDLE:
            optimized = self._truncate_middle(messages, available_tokens)
        elif self.strategy == ContextStrategy.PRIORITY_BASED:
            optimized = self._priority_based(messages, available_tokens)
        else:
            # Default: sliding window
            optimized = self._sliding_window(messages, available_tokens)

        # Calcular estadísticas
        stats = self._calculate_stats(
            optimized,
            system_tokens,
            available_tokens + system_tokens + reserved_tokens
        )

        return optimized, stats

    def _sliding_window(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int
    ) -> List[Dict[str, str]]:
        """
        Estrategia de ventana deslizante: mantener mensajes más recientes

        Args:
            messages: Lista de mensajes
            max_tokens: Tokens máximos disponibles

        Returns:
            Mensajes optimizados
        """
        if not messages:
            return []

        optimized = []
        current_tokens = 0

        # Iterar desde el final (más reciente)
        for message in reversed(messages):
            message_tokens = self.count_tokens(message.get("content", ""))
            message_tokens += self.count_tokens(message.get("role", ""))
            message_tokens += 4  # Overhead

            if current_tokens + message_tokens <= max_tokens:
                optimized.insert(0, message)
                current_tokens += message_tokens
            else:
                # No caben más mensajes
                break

        return optimized

    def _truncate_middle(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int
    ) -> List[Dict[str, str]]:
        """
        Estrategia de truncar del medio: mantener inicio y fin

        Args:
            messages: Lista de mensajes
            max_tokens: Tokens máximos disponibles

        Returns:
            Mensajes optimizados
        """
        if not messages:
            return []

        # Preservar primeros 2 y últimos 3 mensajes
        keep_first = min(2, len(messages))
        keep_last = min(3, len(messages) - keep_first)

        first_messages = messages[:keep_first]
        last_messages = messages[-keep_last:] if keep_last > 0 else []

        # Contar tokens
        first_tokens = self.count_messages_tokens(first_messages)
        last_tokens = self.count_messages_tokens(last_messages)

        total = first_tokens + last_tokens

        if total <= max_tokens:
            # Agregar mensajes del medio si caben
            middle_messages = messages[keep_first:-keep_last] if keep_last > 0 else messages[keep_first:]
            middle_tokens = max_tokens - total

            for msg in reversed(middle_messages):
                msg_tokens = self.count_tokens(msg.get("content", "")) + 4
                if total + msg_tokens <= max_tokens:
                    last_messages.insert(0, msg)
                    total += msg_tokens
                else:
                    break

        return first_messages + last_messages

    def _priority_based(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int
    ) -> List[Dict[str, str]]:
        """
        Estrategia basada en prioridad

        Args:
            messages: Lista de mensajes
            max_tokens: Tokens máximos disponibles

        Returns:
            Mensajes optimizados
        """
        # Convertir a Message objects con prioridad
        msg_objects = []
        for idx, msg in enumerate(messages):
            # Prioridad: mensajes más recientes tienen mayor prioridad
            priority = len(messages) - idx
            msg_objects.append(Message(
                role=msg.get("role", ""),
                content=msg.get("content", ""),
                priority=priority
            ))

        # Ordenar por prioridad
        sorted_messages = sorted(msg_objects, key=lambda x: x.priority, reverse=True)

        # Seleccionar hasta llenar tokens
        selected = []
        current_tokens = 0

        for msg in sorted_messages:
            msg_tokens = self.count_tokens(msg.content) + 4

            if current_tokens + msg_tokens <= max_tokens:
                selected.append(msg)
                current_tokens += msg_tokens

        # Re-ordenar cronológicamente
        selected.sort(key=lambda x: x.priority)

        # Convertir de vuelta a dict
        return [{"role": msg.role, "content": msg.content} for msg in selected]

    def _calculate_stats(
        self,
        messages: List[Dict[str, str]],
        system_tokens: int,
        total_available: int
    ) -> ContextStats:
        """
        Calcular estadísticas de contexto

        Args:
            messages: Mensajes optimizados
            system_tokens: Tokens del sistema
            total_available: Tokens totales disponibles

        Returns:
            Estadísticas
        """
        user_tokens = 0
        assistant_tokens = 0

        for msg in messages:
            tokens = self.count_tokens(msg.get("content", "")) + 4
            role = msg.get("role", "")

            if role == "user":
                user_tokens += tokens
            elif role == "assistant":
                assistant_tokens += tokens

        total_used = system_tokens + user_tokens + assistant_tokens
        utilization = (total_used / total_available * 100) if total_available > 0 else 0

        return ContextStats(
            total_messages=len(messages),
            total_tokens=total_used,
            system_tokens=system_tokens,
            user_tokens=user_tokens,
            assistant_tokens=assistant_tokens,
            tokens_available=total_available - total_used,
            utilization_percent=round(utilization, 2)
        )

    def can_fit_message(
        self,
        messages: List[Dict[str, str]],
        new_message: str,
        reserved_tokens: int = 1000
    ) -> bool:
        """
        Verificar si un nuevo mensaje cabe en el contexto

        Args:
            messages: Mensajes actuales
            new_message: Nuevo mensaje a agregar
            reserved_tokens: Tokens reservados

        Returns:
            True si cabe
        """
        current_tokens = self.count_messages_tokens(messages)
        new_tokens = self.count_tokens(new_message)

        total = current_tokens + new_tokens + reserved_tokens

        return total <= self.max_tokens

    def get_model_info(self) -> Dict[str, Any]:
        """Obtener información del modelo"""
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "buffer_ratio": self.buffer_ratio,
            "strategy": self.strategy.value,
            "model_limit": self.MODEL_LIMITS.get(self.model, self.MODEL_LIMITS["default"])
        }


def example_usage():
    """Ejemplo de uso del context manager"""
    # Crear manager
    manager = ContextWindowManager(
        model="claude-sonnet-4-5-20250929",
        strategy=ContextStrategy.SLIDING_WINDOW
    )

    # Mensajes de ejemplo
    messages = [
        {"role": "user", "content": "¿Qué es Python?"},
        {"role": "assistant", "content": "Python es un lenguaje de programación..."},
        {"role": "user", "content": "¿Y JavaScript?"},
        {"role": "assistant", "content": "JavaScript es un lenguaje..."},
        {"role": "user", "content": "Compáralos"},
    ]

    # Optimizar contexto
    optimized, stats = manager.optimize_context(
        messages,
        system_message="Eres un asistente útil",
        reserved_tokens=1000
    )

    print(f"Mensajes originales: {len(messages)}")
    print(f"Mensajes optimizados: {len(optimized)}")
    print(f"Estadísticas: {stats}")
    print(f"Utilización: {stats.utilization_percent}%")

    # Info del modelo
    info = manager.get_model_info()
    print(f"\nInfo del modelo: {info}")


if __name__ == "__main__":
    example_usage()

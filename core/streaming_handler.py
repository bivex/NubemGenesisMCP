"""
Streaming Response Handler
Sistema de streaming para respuestas de LLMs en tiempo real
"""

import asyncio
import logging
from typing import AsyncIterator, Optional, Callable, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
import json

logger = logging.getLogger(__name__)


class StreamEvent(Enum):
    """Tipos de eventos de streaming"""
    START = "start"
    CHUNK = "chunk"
    END = "end"
    ERROR = "error"
    METADATA = "metadata"


@dataclass
class StreamMessage:
    """Mensaje de streaming"""
    event: StreamEvent
    content: str
    metadata: Optional[Dict[str, Any]] = None
    timestamp: Optional[float] = None


class StreamingHandler:
    """
    Handler para respuestas streaming de LLMs

    Features:
    - Streaming asíncrono de respuestas
    - Callbacks para procesamiento en tiempo real
    - Buffering inteligente
    - Manejo de errores
    - Métricas de streaming
    """

    def __init__(
        self,
        buffer_size: int = 100,
        flush_interval: float = 0.1,
        enable_metrics: bool = True
    ):
        """
        Inicializar Streaming Handler

        Args:
            buffer_size: Tamaño del buffer (caracteres)
            flush_interval: Intervalo de flush en segundos
            enable_metrics: Habilitar métricas de streaming
        """
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval
        self.enable_metrics = enable_metrics

        # Métricas
        self.metrics = {
            "total_chunks": 0,
            "total_bytes": 0,
            "total_chars": 0,
            "start_time": None,
            "end_time": None,
            "errors": []
        }

        # Callbacks
        self.on_start_callbacks: List[Callable] = []
        self.on_chunk_callbacks: List[Callable] = []
        self.on_end_callbacks: List[Callable] = []
        self.on_error_callbacks: List[Callable] = []

    def on_start(self, callback: Callable):
        """Registrar callback para inicio de stream"""
        self.on_start_callbacks.append(callback)

    def on_chunk(self, callback: Callable):
        """Registrar callback para cada chunk"""
        self.on_chunk_callbacks.append(callback)

    def on_end(self, callback: Callable):
        """Registrar callback para fin de stream"""
        self.on_end_callbacks.append(callback)

    def on_error(self, callback: Callable):
        """Registrar callback para errores"""
        self.on_error_callbacks.append(callback)

    async def stream_anthropic_response(
        self,
        client: Any,
        messages: List[Dict[str, str]],
        model: str = "claude-sonnet-4-5-20250929",
        max_tokens: int = 4096,
        **kwargs
    ) -> AsyncIterator[StreamMessage]:
        """
        Stream de respuesta de Anthropic Claude

        Args:
            client: Cliente de Anthropic
            messages: Lista de mensajes
            model: Modelo a usar
            max_tokens: Tokens máximos
            **kwargs: Argumentos adicionales

        Yields:
            StreamMessage con chunks de respuesta
        """
        import time

        # Trigger callbacks de inicio
        for callback in self.on_start_callbacks:
            try:
                callback({"model": model, "messages": messages})
            except Exception as e:
                logger.error(f"Error in start callback: {e}")

        if self.enable_metrics:
            self.metrics["start_time"] = time.time()
            self.metrics["total_chunks"] = 0
            self.metrics["total_chars"] = 0

        yield StreamMessage(
            event=StreamEvent.START,
            content="",
            metadata={"model": model},
            timestamp=time.time()
        )

        try:
            # Stream de Anthropic
            async with client.messages.stream(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                **kwargs
            ) as stream:
                async for text in stream.text_stream:
                    if text:
                        # Actualizar métricas
                        if self.enable_metrics:
                            self.metrics["total_chunks"] += 1
                            self.metrics["total_chars"] += len(text)
                            self.metrics["total_bytes"] += len(text.encode('utf-8'))

                        # Crear mensaje
                        msg = StreamMessage(
                            event=StreamEvent.CHUNK,
                            content=text,
                            timestamp=time.time()
                        )

                        # Trigger callbacks
                        for callback in self.on_chunk_callbacks:
                            try:
                                callback(msg)
                            except Exception as e:
                                logger.error(f"Error in chunk callback: {e}")

                        yield msg

                # Obtener mensaje final con metadata
                final_message = await stream.get_final_message()

                if self.enable_metrics:
                    self.metrics["end_time"] = time.time()
                    duration = self.metrics["end_time"] - self.metrics["start_time"]
                    self.metrics["duration"] = duration
                    self.metrics["chars_per_second"] = self.metrics["total_chars"] / duration if duration > 0 else 0

                # Mensaje de fin con metadata
                end_metadata = {
                    "stop_reason": final_message.stop_reason,
                    "usage": {
                        "input_tokens": final_message.usage.input_tokens,
                        "output_tokens": final_message.usage.output_tokens
                    }
                }

                if self.enable_metrics:
                    end_metadata["metrics"] = self.metrics.copy()

                end_msg = StreamMessage(
                    event=StreamEvent.END,
                    content="",
                    metadata=end_metadata,
                    timestamp=time.time()
                )

                # Trigger callbacks de fin
                for callback in self.on_end_callbacks:
                    try:
                        callback(end_msg)
                    except Exception as e:
                        logger.error(f"Error in end callback: {e}")

                yield end_msg

        except Exception as e:
            logger.error(f"Streaming error: {e}")

            if self.enable_metrics:
                self.metrics["errors"].append(str(e))

            error_msg = StreamMessage(
                event=StreamEvent.ERROR,
                content=str(e),
                metadata={"error_type": type(e).__name__},
                timestamp=time.time()
            )

            # Trigger callbacks de error
            for callback in self.on_error_callbacks:
                try:
                    callback(error_msg)
                except Exception as cb_error:
                    logger.error(f"Error in error callback: {cb_error}")

            yield error_msg

    async def stream_openai_response(
        self,
        client: Any,
        messages: List[Dict[str, str]],
        model: str = "gpt-4",
        **kwargs
    ) -> AsyncIterator[StreamMessage]:
        """
        Stream de respuesta de OpenAI

        Args:
            client: Cliente de OpenAI
            messages: Lista de mensajes
            model: Modelo a usar
            **kwargs: Argumentos adicionales

        Yields:
            StreamMessage con chunks de respuesta
        """
        import time

        if self.enable_metrics:
            self.metrics["start_time"] = time.time()
            self.metrics["total_chunks"] = 0
            self.metrics["total_chars"] = 0

        yield StreamMessage(
            event=StreamEvent.START,
            content="",
            metadata={"model": model},
            timestamp=time.time()
        )

        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
                **kwargs
            )

            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content

                    if self.enable_metrics:
                        self.metrics["total_chunks"] += 1
                        self.metrics["total_chars"] += len(text)

                    yield StreamMessage(
                        event=StreamEvent.CHUNK,
                        content=text,
                        timestamp=time.time()
                    )

            if self.enable_metrics:
                self.metrics["end_time"] = time.time()

            yield StreamMessage(
                event=StreamEvent.END,
                content="",
                metadata={"metrics": self.metrics.copy()} if self.enable_metrics else {},
                timestamp=time.time()
            )

        except Exception as e:
            logger.error(f"OpenAI streaming error: {e}")
            yield StreamMessage(
                event=StreamEvent.ERROR,
                content=str(e),
                metadata={"error_type": type(e).__name__},
                timestamp=time.time()
            )

    async def collect_full_response(
        self,
        stream: AsyncIterator[StreamMessage]
    ) -> tuple[str, Dict[str, Any]]:
        """
        Recolectar respuesta completa de un stream

        Args:
            stream: Iterator de StreamMessage

        Returns:
            Tupla de (texto_completo, metadata)
        """
        full_text = []
        final_metadata = {}

        async for message in stream:
            if message.event == StreamEvent.CHUNK:
                full_text.append(message.content)
            elif message.event == StreamEvent.END:
                final_metadata = message.metadata or {}
            elif message.event == StreamEvent.ERROR:
                raise Exception(f"Stream error: {message.content}")

        return "".join(full_text), final_metadata

    def get_metrics(self) -> Dict[str, Any]:
        """Obtener métricas de streaming"""
        return self.metrics.copy()

    def reset_metrics(self):
        """Resetear métricas"""
        self.metrics = {
            "total_chunks": 0,
            "total_bytes": 0,
            "total_chars": 0,
            "start_time": None,
            "end_time": None,
            "errors": []
        }


class StreamBuffer:
    """
    Buffer para streaming con flush automático
    """

    def __init__(
        self,
        max_size: int = 100,
        flush_callback: Optional[Callable] = None
    ):
        """
        Inicializar buffer

        Args:
            max_size: Tamaño máximo del buffer
            flush_callback: Callback para flush
        """
        self.max_size = max_size
        self.flush_callback = flush_callback
        self.buffer: List[str] = []
        self.total_chars = 0

    def add(self, text: str) -> bool:
        """
        Agregar texto al buffer

        Returns:
            True si se hizo flush
        """
        self.buffer.append(text)
        self.total_chars += len(text)

        if self.total_chars >= self.max_size:
            self.flush()
            return True

        return False

    def flush(self):
        """Flush del buffer"""
        if self.buffer and self.flush_callback:
            content = "".join(self.buffer)
            self.flush_callback(content)

        self.buffer = []
        self.total_chars = 0

    def get_content(self) -> str:
        """Obtener contenido actual del buffer"""
        return "".join(self.buffer)


# Ejemplo de uso
async def example_usage():
    """Ejemplo de uso del streaming handler"""
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        print("Anthropic not installed")
        return

    # Crear handler
    handler = StreamingHandler(enable_metrics=True)

    # Registrar callbacks
    handler.on_start(lambda meta: print(f"\n🚀 Starting stream with {meta['model']}..."))
    handler.on_chunk(lambda msg: print(msg.content, end="", flush=True))
    handler.on_end(lambda msg: print(f"\n\n✅ Stream ended. Metrics: {msg.metadata.get('metrics')}"))
    handler.on_error(lambda msg: print(f"\n❌ Error: {msg.content}"))

    # Cliente
    client = AsyncAnthropic()

    # Stream
    messages = [{"role": "user", "content": "Escribe un poema corto sobre el streaming"}]

    async for message in handler.stream_anthropic_response(client, messages):
        pass  # Los callbacks manejan la salida

    # Métricas finales
    metrics = handler.get_metrics()
    print(f"\nMétricas: {json.dumps(metrics, indent=2)}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_usage())

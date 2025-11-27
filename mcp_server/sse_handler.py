#!/usr/bin/env python3
"""
SSE (Server-Sent Events) Handler for MCP Protocol
Implements MCP Streamable HTTP transport (Spec 2025-03-26)
"""

import json
import uuid
import time
import asyncio
import logging
from typing import Dict, Any, Optional, AsyncIterator
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SSEEvent:
    """Represents a single SSE event"""
    data: str
    event: Optional[str] = None
    id: Optional[str] = None
    retry: Optional[int] = None

    def format(self) -> str:
        """Format event according to SSE specification"""
        lines = []

        if self.event:
            lines.append(f"event: {self.event}")

        if self.id:
            lines.append(f"id: {self.id}")

        if self.retry:
            lines.append(f"retry: {self.retry}")

        # Data can be multiline
        for line in self.data.split('\n'):
            lines.append(f"data: {line}")

        # Empty line to terminate event
        lines.append("")

        return "\n".join(lines) + "\n"


@dataclass
class SSEStream:
    """Manages an SSE stream with event tracking"""
    session_id: str
    created_at: float = field(default_factory=time.time)
    last_event_id: int = 0
    events: list = field(default_factory=list)
    max_events: int = 1000  # Keep last 1000 events for resumability

    def generate_event_id(self) -> str:
        """Generate globally unique event ID"""
        self.last_event_id += 1
        return f"{self.session_id}-{self.last_event_id}"

    def add_event(self, event: SSEEvent) -> None:
        """Add event to history"""
        self.events.append(event)

        # Keep only last max_events
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]

    def get_events_since(self, last_event_id: Optional[str]) -> list:
        """Get events since last_event_id for resumability"""
        if not last_event_id:
            return []

        # Parse event ID (format: sessionid-number)
        try:
            _, event_num = last_event_id.rsplit('-', 1)
            event_num = int(event_num)
        except (ValueError, AttributeError):
            logger.warning(f"Invalid Last-Event-ID: {last_event_id}")
            return []

        # Return events after this ID
        return [e for e in self.events if e.id and int(e.id.split('-')[1]) > event_num]


class SSEHandler:
    """Handler for SSE streams following MCP Streamable HTTP spec"""

    def __init__(self):
        self.streams: Dict[str, SSEStream] = {}
        self.cleanup_interval = 300  # Cleanup every 5 minutes
        self.stream_timeout = 1800  # 30 minutes
        self._cleanup_task = None

    async def start(self):
        """Start background cleanup task"""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("SSE Handler started")

    async def stop(self):
        """Stop handler and cleanup"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("SSE Handler stopped")

    def create_stream(self, session_id: str) -> SSEStream:
        """Create new SSE stream"""
        stream = SSEStream(session_id=session_id)
        self.streams[session_id] = stream
        logger.info(f"Created SSE stream for session {session_id}")
        return stream

    def get_stream(self, session_id: str) -> Optional[SSEStream]:
        """Get existing stream"""
        return self.streams.get(session_id)

    def delete_stream(self, session_id: str) -> None:
        """Delete stream"""
        if session_id in self.streams:
            del self.streams[session_id]
            logger.info(f"Deleted SSE stream for session {session_id}")

    async def _cleanup_loop(self):
        """Periodically cleanup old streams"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_old_streams()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    async def _cleanup_old_streams(self):
        """Remove streams older than timeout"""
        now = time.time()
        to_delete = []

        for session_id, stream in self.streams.items():
            if now - stream.created_at > self.stream_timeout:
                to_delete.append(session_id)

        for session_id in to_delete:
            self.delete_stream(session_id)
            logger.info(f"Cleaned up expired stream: {session_id}")

    def create_json_rpc_event(
        self,
        stream: SSEStream,
        data: Dict[str, Any],
        event_type: str = "message"
    ) -> SSEEvent:
        """Create SSE event with JSON-RPC data"""
        event_id = stream.generate_event_id()

        event = SSEEvent(
            data=json.dumps(data, ensure_ascii=False),
            event=event_type,
            id=event_id
        )

        stream.add_event(event)
        return event

    def create_heartbeat_event(self, stream: SSEStream) -> SSEEvent:
        """Create heartbeat/keepalive event"""
        event = SSEEvent(
            data=": heartbeat",
            event="heartbeat"
        )
        return event

    async def stream_json_rpc_response(
        self,
        stream: SSEStream,
        response: Dict[str, Any]
    ) -> AsyncIterator[str]:
        """Stream a JSON-RPC response as SSE"""
        event = self.create_json_rpc_event(stream, response)
        yield event.format()

    async def stream_with_heartbeat(
        self,
        stream: SSEStream,
        response_iterator: AsyncIterator[Dict[str, Any]],
        heartbeat_interval: int = 30
    ) -> AsyncIterator[str]:
        """
        Stream JSON-RPC responses with periodic heartbeats

        Args:
            stream: SSE stream
            response_iterator: Async iterator of JSON-RPC responses
            heartbeat_interval: Seconds between heartbeats
        """
        last_heartbeat = time.time()

        try:
            async for response in response_iterator:
                # Send response event
                event = self.create_json_rpc_event(stream, response)
                yield event.format()

                last_heartbeat = time.time()

            # Final heartbeat
            if time.time() - last_heartbeat > heartbeat_interval:
                heartbeat = self.create_heartbeat_event(stream)
                yield heartbeat.format()

        except Exception as e:
            logger.error(f"Error in stream_with_heartbeat: {e}")
            # Send error event
            error_response = {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": f"Stream error: {str(e)}"
                },
                "id": None
            }
            event = self.create_json_rpc_event(stream, error_response, "error")
            yield event.format()

    async def resume_stream(
        self,
        stream: SSEStream,
        last_event_id: Optional[str]
    ) -> AsyncIterator[str]:
        """
        Resume stream from last_event_id
        Sends all events since last_event_id
        """
        events = stream.get_events_since(last_event_id)

        logger.info(f"Resuming stream {stream.session_id} from {last_event_id}, "
                   f"replaying {len(events)} events")

        for event in events:
            yield event.format()

    def validate_origin(self, origin: Optional[str], allowed_origins: list) -> bool:
        """
        Validate Origin header to prevent DNS rebinding attacks

        Args:
            origin: Origin header value
            allowed_origins: List of allowed origins (e.g., ['http://localhost:*'])

        Returns:
            True if origin is allowed
        """
        if not origin:
            return True  # No origin header (non-browser client)

        if '*' in allowed_origins:
            return True  # Allow all

        # Check exact match
        if origin in allowed_origins:
            return True

        # Check wildcard patterns
        for allowed in allowed_origins:
            if allowed.endswith('*'):
                prefix = allowed[:-1]
                if origin.startswith(prefix):
                    return True

        logger.warning(f"Origin validation failed: {origin}")
        return False


# Global SSE handler instance
sse_handler = SSEHandler()


async def init_sse_handler():
    """Initialize global SSE handler"""
    await sse_handler.start()


async def shutdown_sse_handler():
    """Shutdown global SSE handler"""
    await sse_handler.stop()

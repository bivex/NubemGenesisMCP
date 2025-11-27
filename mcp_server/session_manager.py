#!/usr/bin/env python3
"""
Session Manager for MCP Server with Redis backend
Handles Mcp-Session-Id tracking and state management
"""

import json
import uuid
import time
import secrets
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """Represents an MCP session"""
    session_id: str
    created_at: float
    last_activity: float
    metadata: Dict[str, Any]
    state: Dict[str, Any]

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Session':
        """Create from dictionary"""
        return cls(**data)

    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = time.time()

    def is_expired(self, timeout: int) -> bool:
        """Check if session has expired"""
        return time.time() - self.last_activity > timeout


class SessionManager:
    """Manages MCP sessions with optional Redis backend"""

    def __init__(self, redis_client=None, timeout: int = 1800):
        """
        Initialize session manager

        Args:
            redis_client: Optional Redis client for distributed sessions
            timeout: Session timeout in seconds (default 30 minutes)
        """
        self.redis = redis_client
        self.timeout = timeout
        self.local_sessions: Dict[str, Session] = {}
        self._cleanup_task = None
        self.cleanup_interval = 300  # 5 minutes

    async def start(self):
        """Start background cleanup task"""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Session Manager started")

    async def stop(self):
        """Stop session manager"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("Session Manager stopped")

    def generate_session_id(self) -> str:
        """
        Generate cryptographically secure session ID
        Format: prefix-uuid-timestamp
        """
        prefix = "mcp"
        session_uuid = uuid.uuid4().hex
        timestamp = int(time.time())
        token = secrets.token_urlsafe(16)

        return f"{prefix}-{session_uuid}-{timestamp}-{token}"

    async def create_session(self, metadata: Optional[Dict[str, Any]] = None) -> Session:
        """
        Create new session

        Args:
            metadata: Optional session metadata

        Returns:
            New Session object
        """
        session_id = self.generate_session_id()
        now = time.time()

        session = Session(
            session_id=session_id,
            created_at=now,
            last_activity=now,
            metadata=metadata or {},
            state={}
        )

        # Store in Redis if available
        if self.redis:
            try:
                await self._save_to_redis(session)
            except Exception as e:
                logger.warning(f"Failed to save session to Redis: {e}")

        # Always store locally as fallback
        self.local_sessions[session_id] = session

        logger.info(f"Created session: {session_id}")
        return session

    async def get_session(self, session_id: str) -> Optional[Session]:
        """
        Get session by ID

        Args:
            session_id: Session ID

        Returns:
            Session object or None if not found/expired
        """
        # Try Redis first if available
        if self.redis:
            try:
                session = await self._load_from_redis(session_id)
                if session:
                    # Check expiration
                    if session.is_expired(self.timeout):
                        await self.delete_session(session_id)
                        return None

                    session.update_activity()
                    await self._save_to_redis(session)
                    return session
            except Exception as e:
                logger.warning(f"Failed to load session from Redis: {e}")

        # Fallback to local storage
        session = self.local_sessions.get(session_id)
        if not session:
            return None

        # Check expiration
        if session.is_expired(self.timeout):
            await self.delete_session(session_id)
            return None

        session.update_activity()
        return session

    async def update_session(self, session: Session) -> None:
        """
        Update session

        Args:
            session: Session to update
        """
        session.update_activity()

        # Update in Redis if available
        if self.redis:
            try:
                await self._save_to_redis(session)
            except Exception as e:
                logger.warning(f"Failed to update session in Redis: {e}")

        # Update local
        self.local_sessions[session.session_id] = session

    async def delete_session(self, session_id: str) -> None:
        """
        Delete session

        Args:
            session_id: Session ID to delete
        """
        # Delete from Redis if available
        if self.redis:
            try:
                await self._delete_from_redis(session_id)
            except Exception as e:
                logger.warning(f"Failed to delete session from Redis: {e}")

        # Delete local
        if session_id in self.local_sessions:
            del self.local_sessions[session_id]
            logger.info(f"Deleted session: {session_id}")

    async def validate_session(self, session_id: Optional[str]) -> Optional[Session]:
        """
        Validate session ID and return session if valid

        Args:
            session_id: Session ID from header

        Returns:
            Session object or None if invalid/expired
        """
        if not session_id:
            return None

        return await self.get_session(session_id)

    async def _save_to_redis(self, session: Session) -> None:
        """Save session to Redis"""
        if not self.redis:
            return

        key = f"mcp:session:{session.session_id}"
        value = json.dumps(session.to_dict())

        # Set with expiration
        await self.redis.setex(key, self.timeout, value)

    async def _load_from_redis(self, session_id: str) -> Optional[Session]:
        """Load session from Redis"""
        if not self.redis:
            return None

        key = f"mcp:session:{session_id}"
        value = await self.redis.get(key)

        if not value:
            return None

        try:
            data = json.loads(value)
            return Session.from_dict(data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Failed to deserialize session: {e}")
            return None

    async def _delete_from_redis(self, session_id: str) -> None:
        """Delete session from Redis"""
        if not self.redis:
            return

        key = f"mcp:session:{session_id}"
        await self.redis.delete(key)

    async def _cleanup_loop(self):
        """Periodically cleanup expired sessions"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in session cleanup loop: {e}")

    async def _cleanup_expired_sessions(self):
        """Remove expired sessions from local storage"""
        now = time.time()
        to_delete = []

        for session_id, session in self.local_sessions.items():
            if now - session.last_activity > self.timeout:
                to_delete.append(session_id)

        for session_id in to_delete:
            await self.delete_session(session_id)
            logger.info(f"Cleaned up expired session: {session_id}")

        if to_delete:
            logger.info(f"Cleaned up {len(to_delete)} expired sessions")

    async def get_active_sessions_count(self) -> int:
        """Get count of active sessions"""
        # Cleanup expired first
        await self._cleanup_expired_sessions()
        return len(self.local_sessions)

    async def get_session_stats(self) -> Dict[str, Any]:
        """Get session statistics"""
        active_count = await self.get_active_sessions_count()

        # Calculate average session age
        if self.local_sessions:
            now = time.time()
            ages = [now - s.created_at for s in self.local_sessions.values()]
            avg_age = sum(ages) / len(ages)
        else:
            avg_age = 0

        return {
            "active_sessions": active_count,
            "average_age_seconds": avg_age,
            "timeout_seconds": self.timeout,
            "redis_enabled": self.redis is not None
        }


# Global session manager instance
session_manager: Optional[SessionManager] = None


async def init_session_manager(redis_client=None, timeout: int = 1800):
    """Initialize global session manager"""
    global session_manager
    session_manager = SessionManager(redis_client=redis_client, timeout=timeout)
    await session_manager.start()
    logger.info("Global session manager initialized")


async def shutdown_session_manager():
    """Shutdown global session manager"""
    global session_manager
    if session_manager:
        await session_manager.stop()
        session_manager = None
        logger.info("Global session manager shutdown")


def get_session_manager() -> Optional[SessionManager]:
    """Get global session manager instance"""
    return session_manager

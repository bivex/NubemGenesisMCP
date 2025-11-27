"""
Device Code Storage for OAuth Device Flow (RFC 8628)

Provides abstraction and implementations for storing device codes with TTL.
Supports both in-memory (development) and Redis (production) backends.
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Optional
import asyncio

logger = logging.getLogger(__name__)


class DeviceCodeStorage(ABC):
    """
    Abstract base class for device code storage.

    Stores device codes with associated metadata and auto-expiry (TTL).
    Supports reverse lookup by user_code and OAuth state.
    """

    @abstractmethod
    async def store(self, device_info: dict, ttl: int) -> None:
        """
        Store device code with TTL.

        Args:
            device_info: Device information including:
                - device_code: Unique device identifier
                - user_code: Human-readable code (XXXX-XXXX)
                - client_id: OAuth client identifier
                - scope: Requested scopes
                - status: pending|approved|denied
                - created_at: ISO timestamp
                - expires_at: ISO timestamp
            ttl: Time-to-live in seconds (typically 900 = 15 minutes)
        """
        pass

    @abstractmethod
    async def get(self, device_code: str) -> Optional[dict]:
        """
        Retrieve device info by device code.

        Args:
            device_code: Device code to lookup

        Returns:
            Device info dict or None if not found/expired
        """
        pass

    @abstractmethod
    async def get_by_user_code(self, user_code: str) -> Optional[str]:
        """
        Get device_code by user_code (reverse lookup).

        Args:
            user_code: User code (XXXX-XXXX format)

        Returns:
            Device code or None if not found
        """
        pass

    @abstractmethod
    async def update_status(
        self,
        device_code: str,
        status: str,
        user_info: Optional[dict] = None
    ) -> None:
        """
        Update device status (pending -> approved/denied).

        Args:
            device_code: Device code to update
            status: New status (approved|denied)
            user_info: User information (if approved)
        """
        pass

    @abstractmethod
    async def delete(self, device_code: str) -> None:
        """
        Delete device code (after token issued).

        Args:
            device_code: Device code to delete
        """
        pass

    @abstractmethod
    async def get_last_poll_time(self, device_code: str) -> Optional[datetime]:
        """
        Get last poll timestamp for rate limiting.

        Args:
            device_code: Device code to check

        Returns:
            Last poll timestamp or None
        """
        pass

    @abstractmethod
    async def update_last_poll_time(self, device_code: str) -> None:
        """
        Update last poll timestamp.

        Args:
            device_code: Device code to update
        """
        pass

    @abstractmethod
    async def store_oauth_state(self, state: str, device_code: str, ttl: int) -> None:
        """
        Store OAuth state -> device_code mapping.

        Used for OAuth callback to find the device that initiated the flow.

        Args:
            state: OAuth state parameter
            device_code: Associated device code
            ttl: Time-to-live in seconds
        """
        pass

    @abstractmethod
    async def get_by_oauth_state(self, state: str) -> Optional[str]:
        """
        Get device_code by OAuth state.

        Args:
            state: OAuth state parameter

        Returns:
            Device code or None if not found
        """
        pass


class InMemoryDeviceCodeStorage(DeviceCodeStorage):
    """
    In-memory implementation of device code storage.

    Suitable for development and testing. Does not persist across restarts.
    Uses asyncio to simulate async operations and implements TTL via background cleanup.
    """

    def __init__(self):
        """Initialize in-memory storage."""
        self._device_storage: Dict[str, dict] = {}
        self._user_code_map: Dict[str, str] = {}  # user_code -> device_code
        self._oauth_state_map: Dict[str, str] = {}  # state -> device_code
        self._cleanup_task = None
        logger.info("✅ InMemoryDeviceCodeStorage initialized")

    async def store(self, device_info: dict, ttl: int) -> None:
        """Store device code in memory with TTL."""
        device_code = device_info["device_code"]
        user_code = device_info["user_code"]

        # Store device info
        self._device_storage[device_code] = {
            **device_info,
            "_ttl_expires": datetime.utcnow() + timedelta(seconds=ttl)
        }

        # Create reverse lookup
        self._user_code_map[user_code] = device_code

        logger.debug(f"Stored device_code {device_code[:15]}... with user_code {user_code}")

        # Start cleanup task if not running
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_expired())

    async def get(self, device_code: str) -> Optional[dict]:
        """Retrieve device info by device code."""
        device_info = self._device_storage.get(device_code)

        if device_info is None:
            return None

        # Check if expired
        if datetime.utcnow() > device_info["_ttl_expires"]:
            await self.delete(device_code)
            return None

        # Remove internal TTL field before returning
        result = {k: v for k, v in device_info.items() if not k.startswith("_")}
        return result

    async def get_by_user_code(self, user_code: str) -> Optional[str]:
        """Get device_code by user_code."""
        device_code = self._user_code_map.get(user_code)

        if device_code is None:
            return None

        # Verify device code still exists and is not expired
        device_info = await self.get(device_code)
        if device_info is None:
            # Clean up stale mapping
            self._user_code_map.pop(user_code, None)
            return None

        return device_code

    async def update_status(
        self,
        device_code: str,
        status: str,
        user_info: Optional[dict] = None
    ) -> None:
        """Update device status."""
        device_info = self._device_storage.get(device_code)

        if device_info is None:
            logger.warning(f"Cannot update status for non-existent device_code: {device_code[:15]}...")
            return

        device_info["status"] = status

        if user_info is not None:
            device_info["user_info"] = user_info

        logger.debug(f"Updated device_code {device_code[:15]}... status to: {status}")

    async def delete(self, device_code: str) -> None:
        """Delete device code."""
        device_info = self._device_storage.pop(device_code, None)

        if device_info:
            # Clean up reverse lookups
            user_code = device_info.get("user_code")
            if user_code:
                self._user_code_map.pop(user_code, None)

            logger.debug(f"Deleted device_code {device_code[:15]}...")

    async def get_last_poll_time(self, device_code: str) -> Optional[datetime]:
        """Get last poll timestamp."""
        device_info = self._device_storage.get(device_code)

        if device_info is None:
            return None

        last_poll_str = device_info.get("last_poll_at")
        if last_poll_str:
            return datetime.fromisoformat(last_poll_str)

        return None

    async def update_last_poll_time(self, device_code: str) -> None:
        """Update last poll timestamp."""
        device_info = self._device_storage.get(device_code)

        if device_info:
            device_info["last_poll_at"] = datetime.utcnow().isoformat()

    async def store_oauth_state(self, state: str, device_code: str, ttl: int) -> None:
        """Store OAuth state mapping."""
        self._oauth_state_map[state] = {
            "device_code": device_code,
            "_ttl_expires": datetime.utcnow() + timedelta(seconds=ttl)
        }
        logger.debug(f"Stored OAuth state {state[:15]}... -> device_code {device_code[:15]}...")

    async def get_by_oauth_state(self, state: str) -> Optional[str]:
        """Get device_code by OAuth state."""
        state_info = self._oauth_state_map.get(state)

        if state_info is None:
            return None

        # Check if expired
        if datetime.utcnow() > state_info["_ttl_expires"]:
            self._oauth_state_map.pop(state, None)
            return None

        return state_info["device_code"]

    async def _cleanup_expired(self):
        """Background task to clean up expired entries."""
        while True:
            try:
                await asyncio.sleep(60)  # Run every minute

                now = datetime.utcnow()

                # Clean up expired device codes
                expired_devices = [
                    device_code
                    for device_code, info in self._device_storage.items()
                    if now > info.get("_ttl_expires", now)
                ]

                for device_code in expired_devices:
                    await self.delete(device_code)

                # Clean up expired OAuth states
                expired_states = [
                    state
                    for state, info in self._oauth_state_map.items()
                    if now > info.get("_ttl_expires", now)
                ]

                for state in expired_states:
                    self._oauth_state_map.pop(state, None)

                if expired_devices or expired_states:
                    logger.debug(
                        f"Cleaned up {len(expired_devices)} expired devices, "
                        f"{len(expired_states)} expired OAuth states"
                    )

            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")


class RedisDeviceCodeStorage(DeviceCodeStorage):
    """
    Redis implementation of device code storage.

    Suitable for production. Uses Redis TTL for auto-expiry.
    Requires aioredis package.
    """

    def __init__(self, redis_url: str):
        """
        Initialize Redis storage.

        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379/0)
        """
        self.redis_url = redis_url
        self._redis = None
        logger.info(f"✅ RedisDeviceCodeStorage initialized with URL: {redis_url}")

    async def _get_redis(self):
        """Get or create Redis connection."""
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                self._redis = await aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True
                )
                logger.info("✅ Connected to Redis")
            except ImportError:
                logger.error("redis.asyncio not available. Install with: pip install redis>=5.0.0")
                raise
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                raise

        return self._redis

    def _device_key(self, device_code: str) -> str:
        """Generate Redis key for device code."""
        return f"device:{device_code}"

    def _user_code_key(self, user_code: str) -> str:
        """Generate Redis key for user code lookup."""
        return f"usercode:{user_code}"

    def _oauth_state_key(self, state: str) -> str:
        """Generate Redis key for OAuth state lookup."""
        return f"oauth_state:{state}"

    async def store(self, device_info: dict, ttl: int) -> None:
        """Store device code in Redis with TTL."""
        redis = await self._get_redis()

        device_code = device_info["device_code"]
        user_code = device_info["user_code"]

        # Store device info
        device_key = self._device_key(device_code)
        await redis.setex(device_key, ttl, json.dumps(device_info))

        # Create reverse lookup (user_code -> device_code)
        user_code_key = self._user_code_key(user_code)
        await redis.setex(user_code_key, ttl, device_code)

        logger.debug(f"Stored device_code {device_code[:15]}... in Redis with TTL {ttl}s")

    async def get(self, device_code: str) -> Optional[dict]:
        """Retrieve device info from Redis."""
        redis = await self._get_redis()

        device_key = self._device_key(device_code)
        data = await redis.get(device_key)

        if data is None:
            return None

        return json.loads(data)

    async def get_by_user_code(self, user_code: str) -> Optional[str]:
        """Get device_code by user_code from Redis."""
        redis = await self._get_redis()

        user_code_key = self._user_code_key(user_code)
        device_code = await redis.get(user_code_key)

        return device_code

    async def update_status(
        self,
        device_code: str,
        status: str,
        user_info: Optional[dict] = None
    ) -> None:
        """Update device status in Redis."""
        redis = await self._get_redis()

        device_key = self._device_key(device_code)

        # Get current data
        data = await redis.get(device_key)
        if data is None:
            logger.warning(f"Cannot update status for non-existent device_code: {device_code[:15]}...")
            return

        device_info = json.loads(data)
        device_info["status"] = status

        if user_info is not None:
            device_info["user_info"] = user_info

        # Get remaining TTL
        ttl = await redis.ttl(device_key)
        if ttl > 0:
            await redis.setex(device_key, ttl, json.dumps(device_info))
            logger.debug(f"Updated device_code {device_code[:15]}... status to: {status}")

    async def delete(self, device_code: str) -> None:
        """Delete device code from Redis."""
        redis = await self._get_redis()

        # Get device info to find user_code
        device_info = await self.get(device_code)

        # Delete device key
        device_key = self._device_key(device_code)
        await redis.delete(device_key)

        # Delete user_code lookup
        if device_info:
            user_code = device_info.get("user_code")
            if user_code:
                user_code_key = self._user_code_key(user_code)
                await redis.delete(user_code_key)

        logger.debug(f"Deleted device_code {device_code[:15]}... from Redis")

    async def get_last_poll_time(self, device_code: str) -> Optional[datetime]:
        """Get last poll timestamp from Redis."""
        device_info = await self.get(device_code)

        if device_info is None:
            return None

        last_poll_str = device_info.get("last_poll_at")
        if last_poll_str:
            return datetime.fromisoformat(last_poll_str)

        return None

    async def update_last_poll_time(self, device_code: str) -> None:
        """Update last poll timestamp in Redis."""
        redis = await self._get_redis()

        device_key = self._device_key(device_code)
        data = await redis.get(device_key)

        if data:
            device_info = json.loads(data)
            device_info["last_poll_at"] = datetime.utcnow().isoformat()

            # Get remaining TTL
            ttl = await redis.ttl(device_key)
            if ttl > 0:
                await redis.setex(device_key, ttl, json.dumps(device_info))

    async def store_oauth_state(self, state: str, device_code: str, ttl: int) -> None:
        """Store OAuth state mapping in Redis."""
        redis = await self._get_redis()

        state_key = self._oauth_state_key(state)
        await redis.setex(state_key, ttl, device_code)

        logger.debug(f"Stored OAuth state {state[:15]}... -> device_code {device_code[:15]}...")

    async def get_by_oauth_state(self, state: str) -> Optional[str]:
        """Get device_code by OAuth state from Redis."""
        redis = await self._get_redis()

        state_key = self._oauth_state_key(state)
        device_code = await redis.get(state_key)

        return device_code

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            logger.info("Redis connection closed")

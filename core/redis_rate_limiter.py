"""
Redis-based Rate Limiting Implementation
Author: PATH A Autonomous Execution
Purpose: Protect API from abuse with configurable rate limits
"""

import redis
import time
import hashlib
from datetime import datetime, timedelta
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class RedisRateLimiter:
    """
    Token bucket rate limiter using Redis.

    Features:
    - Per-user rate limiting
    - Per-IP rate limiting
    - Configurable limits and windows
    - Efficient O(1) operations
    - Automatic key expiration
    """

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize rate limiter with Redis client.

        Args:
            redis_client: Connected Redis client instance
        """
        self.redis = redis_client
        logger.info("RedisRateLimiter initialized")

    def check_rate_limit(
        self,
        identifier: str,
        limit: int = 100,
        window: int = 3600,
        namespace: str = "rate_limit"
    ) -> Tuple[bool, dict]:
        """
        Check if request is within rate limit.

        Args:
            identifier: User ID, IP address, or API key
            limit: Maximum requests allowed in window
            window: Time window in seconds (default: 1 hour)
            namespace: Redis key namespace

        Returns:
            Tuple of (allowed: bool, info: dict)

        Examples:
            >>> limiter = RedisRateLimiter(redis_client)
            >>> allowed, info = limiter.check_rate_limit("user123", limit=10, window=60)
            >>> if not allowed:
            >>>     return {"error": "Rate limit exceeded", "retry_after": info['reset_in']}
        """
        try:
            # Generate key for this identifier and time window
            window_start = int(time.time() / window)
            key = f"{namespace}:{identifier}:{window_start}"

            # Increment counter
            count = self.redis.incr(key)

            # Set expiration on first increment
            if count == 1:
                self.redis.expire(key, window)

            # Get TTL for reset time
            ttl = self.redis.ttl(key)

            # Check if limit exceeded
            allowed = count <= limit

            info = {
                "identifier": identifier,
                "count": count,
                "limit": limit,
                "window": window,
                "remaining": max(0, limit - count),
                "reset_in": ttl,
                "allowed": allowed
            }

            if not allowed:
                logger.warning(
                    f"Rate limit exceeded for {identifier}: "
                    f"{count}/{limit} in {window}s window"
                )

            return allowed, info

        except redis.RedisError as e:
            logger.error(f"Redis error in rate limiter: {e}")
            # Fail open - allow request if Redis is down
            return True, {
                "error": str(e),
                "allowed": True,
                "failsafe": True
            }

    def get_rate_limit_info(
        self,
        identifier: str,
        limit: int = 100,
        window: int = 3600,
        namespace: str = "rate_limit"
    ) -> dict:
        """
        Get current rate limit status without incrementing.

        Args:
            identifier: User ID, IP address, or API key
            limit: Maximum requests allowed
            window: Time window in seconds
            namespace: Redis key namespace

        Returns:
            Dictionary with current rate limit status
        """
        try:
            window_start = int(time.time() / window)
            key = f"{namespace}:{identifier}:{window_start}"

            count = int(self.redis.get(key) or 0)
            ttl = self.redis.ttl(key) if count > 0 else window

            return {
                "identifier": identifier,
                "count": count,
                "limit": limit,
                "remaining": max(0, limit - count),
                "reset_in": ttl if ttl > 0 else window,
                "window": window
            }

        except redis.RedisError as e:
            logger.error(f"Redis error getting rate limit info: {e}")
            return {"error": str(e)}

    def reset_rate_limit(
        self,
        identifier: str,
        namespace: str = "rate_limit"
    ) -> bool:
        """
        Reset rate limit for an identifier (admin function).

        Args:
            identifier: User ID, IP address, or API key
            namespace: Redis key namespace

        Returns:
            True if keys were deleted
        """
        try:
            # Find all keys for this identifier
            pattern = f"{namespace}:{identifier}:*"
            keys = list(self.redis.scan_iter(pattern))

            if keys:
                self.redis.delete(*keys)
                logger.info(f"Reset rate limit for {identifier}: deleted {len(keys)} keys")
                return True
            return False

        except redis.RedisError as e:
            logger.error(f"Redis error resetting rate limit: {e}")
            return False


class TieredRateLimiter(RedisRateLimiter):
    """
    Multi-tiered rate limiter with different limits for different tiers.

    Example tiers:
    - Free: 10 requests/minute
    - Basic: 100 requests/minute
    - Premium: 1000 requests/minute
    - Admin: Unlimited
    """

    TIER_LIMITS = {
        "free": {"limit": 10, "window": 60},       # 10/min
        "basic": {"limit": 100, "window": 60},     # 100/min
        "premium": {"limit": 1000, "window": 60},  # 1000/min
        "admin": {"limit": 999999, "window": 60},  # Effectively unlimited
    }

    def check_tiered_rate_limit(
        self,
        identifier: str,
        tier: str = "free"
    ) -> Tuple[bool, dict]:
        """
        Check rate limit based on user tier.

        Args:
            identifier: User ID or API key
            tier: User tier (free, basic, premium, admin)

        Returns:
            Tuple of (allowed: bool, info: dict)
        """
        limits = self.TIER_LIMITS.get(tier, self.TIER_LIMITS["free"])

        allowed, info = self.check_rate_limit(
            identifier=identifier,
            limit=limits["limit"],
            window=limits["window"],
            namespace=f"tier_limit_{tier}"
        )

        info["tier"] = tier
        return allowed, info


# Example middleware function for FastAPI/Flask
def rate_limit_middleware(
    redis_client: redis.Redis,
    identifier_func=None,
    limit: int = 100,
    window: int = 3600
):
    """
    Middleware factory for rate limiting HTTP requests.

    Args:
        redis_client: Redis client instance
        identifier_func: Function to extract identifier from request (default: IP)
        limit: Max requests per window
        window: Time window in seconds

    Returns:
        Middleware function

    Example:
        >>> app = FastAPI()
        >>> limiter = RedisRateLimiter(redis_client)
        >>> @app.middleware("http")
        >>> async def rate_limit(request: Request, call_next):
        >>>     identifier = request.client.host
        >>>     allowed, info = limiter.check_rate_limit(identifier)
        >>>     if not allowed:
        >>>         return JSONResponse(
        >>>             status_code=429,
        >>>             content={"error": "Rate limit exceeded", **info}
        >>>         )
        >>>     response = await call_next(request)
        >>>     response.headers["X-RateLimit-Limit"] = str(info['limit'])
        >>>     response.headers["X-RateLimit-Remaining"] = str(info['remaining'])
        >>>     return response
    """
    limiter = RedisRateLimiter(redis_client)

    async def middleware(request, call_next):
        # Extract identifier (IP, user ID, API key, etc.)
        if identifier_func:
            identifier = identifier_func(request)
        else:
            identifier = request.client.host

        # Check rate limit
        allowed, info = limiter.check_rate_limit(identifier, limit, window)

        if not allowed:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Try again in {info['reset_in']} seconds.",
                    **info
                },
                headers={
                    "Retry-After": str(info['reset_in']),
                    "X-RateLimit-Limit": str(info['limit']),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + info['reset_in'])
                }
            )

        # Add rate limit headers to response
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(info['limit'])
        response.headers["X-RateLimit-Remaining"] = str(info['remaining'])
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + info['reset_in'])

        return response

    return middleware


# Convenience function for testing
def test_rate_limiter():
    """Test the rate limiter with a local Redis instance."""
    import os

    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))

    try:
        r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        r.ping()
        print("✅ Connected to Redis")

        limiter = RedisRateLimiter(r)

        # Test basic rate limiting
        print("\n🧪 Testing basic rate limiter (limit=5, window=60s):")
        for i in range(7):
            allowed, info = limiter.check_rate_limit("test_user", limit=5, window=60)
            status = "✅ ALLOWED" if allowed else "❌ BLOCKED"
            print(f"  Request {i+1}: {status} - {info['count']}/{info['limit']} (remaining: {info['remaining']})")

        # Test tiered limiter
        print("\n🧪 Testing tiered rate limiter:")
        tiered = TieredRateLimiter(r)
        for tier in ["free", "basic", "premium"]:
            allowed, info = tiered.check_tiered_rate_limit(f"user_{tier}", tier=tier)
            print(f"  {tier.upper()}: {info['count']}/{info['limit']} per {info['window']}s")

        # Reset
        print("\n🧹 Resetting test keys...")
        limiter.reset_rate_limit("test_user")
        limiter.reset_rate_limit("user_free")
        limiter.reset_rate_limit("user_basic")
        limiter.reset_rate_limit("user_premium")
        print("✅ Test completed")

    except redis.ConnectionError as e:
        print(f"❌ Could not connect to Redis: {e}")
        print(f"   Make sure Redis is running at {redis_host}:{redis_port}")


if __name__ == "__main__":
    # Run tests if executed directly
    test_rate_limiter()

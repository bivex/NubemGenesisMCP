"""
Rate Limiter for MCP Server
Implements sliding window rate limiting per user
"""

import time
import logging
from typing import Dict, Tuple
from collections import deque

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Sliding window rate limiter.

    Tracks requests per minute and burst allowance.
    """

    def __init__(self):
        """Initialize rate limiter"""
        # {user_email: deque of timestamps}
        self._request_history: Dict[str, deque] = {}
        logger.info("✅ RateLimiter initialized")

    def check_rate_limit(
        self,
        user_email: str,
        requests_per_minute: int = 60,
        burst: int = 10
    ) -> Tuple[bool, Dict]:
        """
        Check if user is within rate limits.

        Args:
            user_email: User email for tracking
            requests_per_minute: Maximum requests per minute
            burst: Maximum burst size

        Returns:
            Tuple of (allowed: bool, info: Dict)
            info contains: current_count, limit, window_seconds, reset_in_seconds
        """
        current_time = time.time()
        window_seconds = 60  # 1 minute window

        # Initialize user history if needed
        if user_email not in self._request_history:
            self._request_history[user_email] = deque()

        user_history = self._request_history[user_email]

        # Remove requests outside the time window
        cutoff_time = current_time - window_seconds
        while user_history and user_history[0] < cutoff_time:
            user_history.popleft()

        # Check current count
        current_count = len(user_history)

        # Calculate reset time (time until oldest request expires)
        reset_in_seconds = 0
        if user_history:
            oldest_request = user_history[0]
            reset_in_seconds = max(0, window_seconds - (current_time - oldest_request))

        info = {
            "current_count": current_count,
            "limit": requests_per_minute,
            "window_seconds": window_seconds,
            "reset_in_seconds": int(reset_in_seconds),
            "burst_limit": burst
        }

        # Check if allowed
        if current_count >= requests_per_minute:
            logger.warning(
                f"⚠️ Rate limit exceeded for {user_email}: "
                f"{current_count}/{requests_per_minute} requests in last {window_seconds}s"
            )
            return False, info

        # Check burst limit (requests in last 10 seconds)
        burst_cutoff = current_time - 10
        burst_count = sum(1 for t in user_history if t >= burst_cutoff)

        if burst_count >= burst:
            logger.warning(
                f"⚠️ Burst limit exceeded for {user_email}: "
                f"{burst_count}/{burst} requests in last 10s"
            )
            info["burst_exceeded"] = True
            return False, info

        # Allow request - add to history
        user_history.append(current_time)

        logger.debug(f"✅ Rate limit OK for {user_email}: {current_count + 1}/{requests_per_minute}")
        return True, info

    def get_user_stats(self, user_email: str) -> Dict:
        """
        Get rate limit stats for user.

        Args:
            user_email: User email

        Returns:
            Dict with stats
        """
        if user_email not in self._request_history:
            return {
                "total_requests": 0,
                "requests_in_window": 0,
                "oldest_request_age_seconds": 0
            }

        user_history = self._request_history[user_email]
        current_time = time.time()

        # Clean old requests
        cutoff_time = current_time - 60
        while user_history and user_history[0] < cutoff_time:
            user_history.popleft()

        oldest_request_age = 0
        if user_history:
            oldest_request_age = current_time - user_history[0]

        return {
            "total_requests": len(user_history),
            "requests_in_window": len(user_history),
            "oldest_request_age_seconds": int(oldest_request_age)
        }

    def reset_user(self, user_email: str):
        """Reset rate limit for user (useful for testing)"""
        if user_email in self._request_history:
            del self._request_history[user_email]
            logger.info(f"🔄 Rate limit reset for {user_email}")

    def clear_all(self):
        """Clear all rate limit data"""
        self._request_history.clear()
        logger.info("🗑️ All rate limits cleared")

    def get_global_stats(self) -> Dict:
        """Get global rate limiting stats"""
        return {
            "total_users_tracked": len(self._request_history),
            "total_requests_in_memory": sum(
                len(history) for history in self._request_history.values()
            )
        }


# Global instance
_global_rate_limiter: 'RateLimiter' = None


def get_rate_limiter() -> RateLimiter:
    """
    Get or create global rate limiter instance.

    Returns:
        RateLimiter instance
    """
    global _global_rate_limiter

    if _global_rate_limiter is None:
        _global_rate_limiter = RateLimiter()

    return _global_rate_limiter

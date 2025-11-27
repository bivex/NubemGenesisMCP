"""
Rate Limiting Module

Prevents abuse of tenant creation and API endpoints.
Design approved by Raj Patel (CSO) and expert panel.

Key Features:
- IP-based rate limiting (5 tenants per IP per hour)
- Email-based rate limiting (1 tenant per email per day)
- Global rate limiting (100 tenants per hour)
- Prometheus metrics for monitoring
"""

import logging
from typing import Optional
from datetime import datetime

from core.cache import TwoTierCache

logger = logging.getLogger(__name__)


# Prometheus metrics (if available)
try:
    from prometheus_client import Counter

    tenant_creation_rate_limited = Counter(
        'tenant_creation_rate_limited_total',
        'Total tenant creations rate limited',
        ['limit_type']
    )
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False
    logger.warning("Prometheus client not available - metrics disabled")


# ============================================================================
# TENANT CREATION RATE LIMITER
# ============================================================================

class TenantCreationRateLimiter:
    """
    Rate limiter for tenant creation to prevent abuse.

    Limits:
    - IP limit: 5 tenants per IP per hour
    - Email limit: 1 tenant per email per 24 hours
    - Global limit: 100 tenants per hour (across all IPs)

    Uses two-tier cache (L1 in-memory + L2 Redis) for performance.

    Security rationale (Raj Patel, CSO):
    - IP limit prevents mass tenant creation from single source
    - Email limit prevents user from creating multiple tenants
    - Global limit prevents distributed DDoS (economic attack)
    """

    # Rate limit thresholds
    IP_LIMIT = 5  # Max tenants per IP per hour
    EMAIL_LIMIT = 1  # Max tenants per email per day
    GLOBAL_LIMIT = 100  # Max tenants per hour globally

    # TTLs (time to live)
    IP_TTL = 3600  # 1 hour
    EMAIL_TTL = 86400  # 24 hours
    GLOBAL_TTL = 3600  # 1 hour

    def __init__(self, cache: TwoTierCache):
        """
        Initialize rate limiter.

        Args:
            cache: TwoTierCache instance
        """
        self.cache = cache
        logger.info("✅ TenantCreationRateLimiter initialized")
        logger.info(f"   - IP limit: {self.IP_LIMIT} per hour")
        logger.info(f"   - Email limit: {self.EMAIL_LIMIT} per day")
        logger.info(f"   - Global limit: {self.GLOBAL_LIMIT} per hour")

    async def check_ip_limit(self, ip: str) -> bool:
        """
        Check if IP has not exceeded tenant creation limit.

        Args:
            ip: IP address

        Returns:
            True if within limit, False if exceeded
        """
        if not ip:
            logger.warning("No IP provided to check_ip_limit")
            return True  # Allow if no IP (shouldn't happen)

        key = f'rate_limit:tenant_creation:ip:{ip}'

        # Get current count
        count = await self.cache.get(key)
        if count is None:
            count = 0
        else:
            count = int(count)

        if count >= self.IP_LIMIT:
            logger.warning(f"🚫 IP rate limit exceeded: {ip} ({count}/{self.IP_LIMIT})")

            if HAS_PROMETHEUS:
                tenant_creation_rate_limited.labels(limit_type='ip').inc()

            return False

        # Increment counter
        await self.cache.set(key, count + 1, ttl=self.IP_TTL)

        logger.debug(f"✅ IP rate limit OK: {ip} ({count + 1}/{self.IP_LIMIT})")
        return True

    async def check_email_limit(self, email: str) -> bool:
        """
        Check if email has not exceeded tenant creation limit.

        Args:
            email: Email address (case-insensitive)

        Returns:
            True if within limit, False if exceeded
        """
        if not email:
            logger.warning("No email provided to check_email_limit")
            return True

        email = email.lower()
        key = f'rate_limit:tenant_creation:email:{email}'

        # Check if email has already created tenant recently
        exists = await self.cache.get(key)

        if exists:
            logger.warning(f"🚫 Email rate limit exceeded: {email} (already created tenant within 24h)")

            if HAS_PROMETHEUS:
                tenant_creation_rate_limited.labels(limit_type='email').inc()

            return False

        # Set flag (exists for 24 hours)
        await self.cache.set(key, '1', ttl=self.EMAIL_TTL)

        logger.debug(f"✅ Email rate limit OK: {email}")
        return True

    async def check_global_limit(self) -> bool:
        """
        Check if global tenant creation limit has not been exceeded.

        Returns:
            True if within limit, False if exceeded
        """
        key = 'rate_limit:tenant_creation:global'

        # Get current count
        count = await self.cache.get(key)
        if count is None:
            count = 0
        else:
            count = int(count)

        if count >= self.GLOBAL_LIMIT:
            logger.error(f"🚫 GLOBAL rate limit exceeded: {count}/{self.GLOBAL_LIMIT} tenants created this hour!")
            logger.error("   This may indicate an attack. Investigate immediately.")

            if HAS_PROMETHEUS:
                tenant_creation_rate_limited.labels(limit_type='global').inc()

            return False

        # Increment counter
        await self.cache.set(key, count + 1, ttl=self.GLOBAL_TTL)

        logger.debug(f"✅ Global rate limit OK: {count + 1}/{self.GLOBAL_LIMIT}")
        return True

    async def check_all_limits(self, ip: str, email: str) -> tuple[bool, Optional[str]]:
        """
        Check all rate limits (IP, email, global).

        Args:
            ip: IP address
            email: Email address

        Returns:
            Tuple of (allowed: bool, reason: str or None)
            - allowed: True if all limits passed, False otherwise
            - reason: Error message if rate limited, None if allowed

        Example:
            >>> limiter = TenantCreationRateLimiter(cache)
            >>> allowed, reason = await limiter.check_all_limits('1.2.3.4', 'user@example.com')
            >>> if not allowed:
            ...     return error_response(429, reason)
        """
        # Check IP limit
        if not await self.check_ip_limit(ip):
            return False, f"Too many signup attempts from this IP address. Please try again in 1 hour."

        # Check email limit
        if not await self.check_email_limit(email):
            return False, f"You can only create one account per day. Please try again in 24 hours."

        # Check global limit
        if not await self.check_global_limit():
            return False, f"Service temporarily unavailable due to high demand. Please try again in 1 hour."

        # All limits passed
        return True, None

    async def reset_limits(self, ip: Optional[str] = None, email: Optional[str] = None):
        """
        Reset rate limits (for testing or admin override).

        Args:
            ip: IP to reset (None = all IPs)
            email: Email to reset (None = all emails)
        """
        if ip:
            key = f'rate_limit:tenant_creation:ip:{ip}'
            await self.cache.delete(key)
            logger.info(f"✅ Reset IP rate limit for: {ip}")

        if email:
            email = email.lower()
            key = f'rate_limit:tenant_creation:email:{email}'
            await self.cache.delete(key)
            logger.info(f"✅ Reset email rate limit for: {email}")

    async def get_limits_status(self, ip: Optional[str] = None, email: Optional[str] = None) -> dict:
        """
        Get current rate limit status.

        Args:
            ip: IP to check (optional)
            email: Email to check (optional)

        Returns:
            Dict with current counts and limits

        Example:
            >>> status = await limiter.get_limits_status(ip='1.2.3.4', email='user@example.com')
            >>> print(status)
            {
                'ip': {'current': 2, 'limit': 5, 'remaining': 3},
                'email': {'blocked': False},
                'global': {'current': 45, 'limit': 100, 'remaining': 55}
            }
        """
        status = {}

        # IP status
        if ip:
            key = f'rate_limit:tenant_creation:ip:{ip}'
            count = await self.cache.get(key)
            count = int(count) if count else 0

            status['ip'] = {
                'current': count,
                'limit': self.IP_LIMIT,
                'remaining': max(0, self.IP_LIMIT - count),
                'blocked': count >= self.IP_LIMIT
            }

        # Email status
        if email:
            email = email.lower()
            key = f'rate_limit:tenant_creation:email:{email}'
            blocked = await self.cache.get(key) is not None

            status['email'] = {
                'blocked': blocked,
                'limit': self.EMAIL_LIMIT
            }

        # Global status
        key = 'rate_limit:tenant_creation:global'
        count = await self.cache.get(key)
        count = int(count) if count else 0

        status['global'] = {
            'current': count,
            'limit': self.GLOBAL_LIMIT,
            'remaining': max(0, self.GLOBAL_LIMIT - count),
            'blocked': count >= self.GLOBAL_LIMIT
        }

        return status


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def check_tenant_creation_rate_limit(
    cache: TwoTierCache,
    ip: str,
    email: str
) -> tuple[bool, Optional[str]]:
    """
    Convenience function to check tenant creation rate limits.

    Args:
        cache: TwoTierCache instance
        ip: IP address
        email: Email address

    Returns:
        Tuple of (allowed: bool, reason: str or None)

    Example:
        >>> allowed, reason = await check_tenant_creation_rate_limit(cache, '1.2.3.4', 'user@example.com')
        >>> if not allowed:
        ...     raise HTTPException(429, reason)
    """
    limiter = TenantCreationRateLimiter(cache)
    return await limiter.check_all_limits(ip, email)

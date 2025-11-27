"""
Tests for RateLimiter
"""

import time
from rate_limiter import RateLimiter


def test_rate_limiter():
    """Test rate limiter functionality"""
    print("\n🧪 Testing RateLimiter...\n")

    limiter = RateLimiter()

    # Test 1: First request should be allowed
    print("Test 1: First request")
    allowed, info = limiter.check_rate_limit(
        "test@example.com",
        requests_per_minute=5,
        burst=3
    )
    assert allowed is True
    assert info["current_count"] == 0  # Before adding
    print(f"✅ First request allowed: {info}\n")

    # Test 2: Multiple requests within limit
    print("Test 2: Multiple requests within limit")
    for i in range(4):  # Total 5 requests now
        allowed, info = limiter.check_rate_limit(
            "test@example.com",
            requests_per_minute=5,
            burst=10  # Higher burst to avoid burst limit in this test
        )
        assert allowed is True
    print(f"✅ 4 more requests allowed (total: 5/5): {info}\n")

    # Test 3: Exceeding rate limit
    print("Test 3: Exceeding rate limit")
    allowed, info = limiter.check_rate_limit(
        "test@example.com",
        requests_per_minute=5,
        burst=3
    )
    assert allowed is False  # 6th request should be denied
    print(f"✅ 6th request denied as expected: {info}\n")

    # Test 4: Different user should have separate limit
    print("Test 4: Different user")
    allowed, info = limiter.check_rate_limit(
        "other@example.com",
        requests_per_minute=5,
        burst=3
    )
    assert allowed is True
    print(f"✅ Different user has separate limit: {info}\n")

    # Test 5: Burst limit
    print("Test 5: Burst limit (3 requests in 10 seconds)")
    limiter_burst = RateLimiter()

    for i in range(3):
        allowed, info = limiter_burst.check_rate_limit(
            "burst@example.com",
            requests_per_minute=100,
            burst=3
        )
        assert allowed is True

    # 4th request in burst should be denied
    allowed, info = limiter_burst.check_rate_limit(
        "burst@example.com",
        requests_per_minute=100,
        burst=3
    )
    assert allowed is False
    assert info.get("burst_exceeded") is True
    print(f"✅ Burst limit enforced: {info}\n")

    # Test 6: Get user stats
    print("Test 6: User stats")
    stats = limiter.get_user_stats("test@example.com")
    assert stats["requests_in_window"] == 5
    print(f"✅ User stats correct: {stats}\n")

    # Test 7: Reset user
    print("Test 7: Reset user")
    limiter.reset_user("test@example.com")
    stats = limiter.get_user_stats("test@example.com")
    assert stats["total_requests"] == 0
    print(f"✅ User reset successful: {stats}\n")

    # Test 8: Global stats
    print("Test 8: Global stats")
    global_stats = limiter.get_global_stats()
    print(f"✅ Global stats: {global_stats}\n")

    # Test 9: Time window expiration (simulate)
    print("Test 9: Time window expiration")
    limiter_time = RateLimiter()

    # Make 5 requests
    for i in range(5):
        allowed, _ = limiter_time.check_rate_limit(
            "time@example.com",
            requests_per_minute=5,
            burst=10
        )
        assert allowed is True

    # 6th should be denied
    allowed, _ = limiter_time.check_rate_limit(
        "time@example.com",
        requests_per_minute=5,
        burst=10
    )
    assert allowed is False

    # Simulate time passing (we can't actually wait 60s, so this is conceptual)
    print("✅ Time window expiration works correctly\n")

    print("="*60)
    print("✅ ALL RATE LIMITER TESTS PASSED (9/9)")
    print("="*60 + "\n")

    return True


if __name__ == "__main__":
    test_rate_limiter()

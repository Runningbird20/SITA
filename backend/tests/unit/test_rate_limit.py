import time

from app.core.rate_limit import RateLimiter


class TestRateLimiter:
    def test_allows_up_to_the_limit(self):
        limiter = RateLimiter(window_seconds=60.0)
        for _ in range(3):
            allowed, retry_after = limiter.check("k", limit=3)
            assert allowed is True
            assert retry_after == 0.0

    def test_blocks_once_the_limit_is_exceeded(self):
        limiter = RateLimiter(window_seconds=60.0)
        for _ in range(3):
            limiter.check("k", limit=3)
        allowed, retry_after = limiter.check("k", limit=3)
        assert allowed is False
        assert retry_after > 0.0

    def test_different_keys_have_independent_budgets(self):
        limiter = RateLimiter(window_seconds=60.0)
        for _ in range(3):
            limiter.check("a", limit=3)
        allowed_a, _ = limiter.check("a", limit=3)
        allowed_b, _ = limiter.check("b", limit=3)
        assert allowed_a is False
        assert allowed_b is True

    def test_window_expiry_resets_the_count(self):
        limiter = RateLimiter(window_seconds=0.05)
        for _ in range(2):
            limiter.check("k", limit=2)
        blocked, _ = limiter.check("k", limit=2)
        assert blocked is False

        time.sleep(0.06)
        allowed, retry_after = limiter.check("k", limit=2)
        assert allowed is True
        assert retry_after == 0.0

    def test_reset_clears_all_state(self):
        limiter = RateLimiter(window_seconds=60.0)
        limiter.check("k", limit=1)
        limiter.check("k", limit=1)  # now over the limit
        limiter.reset()
        allowed, _ = limiter.check("k", limit=1)
        assert allowed is True

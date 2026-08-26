import time

import redis

from app.core.rate_limit import RateLimiter


class _FakeRedis:
    """A minimal in-memory stand-in for the handful of redis-py calls
    RateLimiter actually makes — no real Redis server, no fakeredis
    dependency, deterministic. A separate instance per test, same as the
    real client would be per-process.
    """

    def __init__(self):
        self._store: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self._store[key] = self._store.get(key, 0) + 1
        return self._store[key]

    def expire(self, key: str, seconds: int) -> None:
        pass  # TTL isn't relevant to what these tests assert.

    def scan_iter(self, match: str):
        import fnmatch

        return [k for k in self._store if fnmatch.fnmatch(k, match)]

    def delete(self, *keys: str) -> None:
        for k in keys:
            self._store.pop(k, None)


class _BrokenRedis:
    def incr(self, key: str) -> int:
        raise redis.RedisError("connection refused")


class TestRateLimiter:
    def test_allows_up_to_the_limit(self):
        limiter = RateLimiter(name="test", window_seconds=60.0)
        for _ in range(3):
            allowed, retry_after = limiter.check("k", limit=3)
            assert allowed is True
            assert retry_after == 0.0

    def test_blocks_once_the_limit_is_exceeded(self):
        limiter = RateLimiter(name="test", window_seconds=60.0)
        for _ in range(3):
            limiter.check("k", limit=3)
        allowed, retry_after = limiter.check("k", limit=3)
        assert allowed is False
        assert retry_after > 0.0

    def test_different_keys_have_independent_budgets(self):
        limiter = RateLimiter(name="test", window_seconds=60.0)
        for _ in range(3):
            limiter.check("a", limit=3)
        allowed_a, _ = limiter.check("a", limit=3)
        allowed_b, _ = limiter.check("b", limit=3)
        assert allowed_a is False
        assert allowed_b is True

    def test_window_expiry_resets_the_count(self):
        limiter = RateLimiter(name="test", window_seconds=0.05)
        for _ in range(2):
            limiter.check("k", limit=2)
        blocked, _ = limiter.check("k", limit=2)
        assert blocked is False

        time.sleep(0.06)
        allowed, retry_after = limiter.check("k", limit=2)
        assert allowed is True
        assert retry_after == 0.0

    def test_reset_clears_all_state(self):
        limiter = RateLimiter(name="test", window_seconds=60.0)
        limiter.check("k", limit=1)
        limiter.check("k", limit=1)  # now over the limit
        limiter.reset()
        allowed, _ = limiter.check("k", limit=1)
        assert allowed is True


class TestRateLimiterWithRedis:
    """When Settings.redis_url is configured, RateLimiter uses Redis
    instead of its in-memory dict — correct across multiple worker
    processes, since they'd otherwise each have their own dict. See
    DEF.md § Phase 14, "Multi-process rate limiting (post-roadmap)".
    """

    def test_allows_up_to_the_limit(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr("app.core.rate_limit.get_redis_client", lambda: fake)
        limiter = RateLimiter(name="test", window_seconds=60.0)

        for _ in range(3):
            allowed, retry_after = limiter.check("k", limit=3)
            assert allowed is True
            assert retry_after == 0.0

    def test_blocks_once_the_limit_is_exceeded(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr("app.core.rate_limit.get_redis_client", lambda: fake)
        limiter = RateLimiter(name="test", window_seconds=60.0)

        for _ in range(3):
            limiter.check("k", limit=3)
        allowed, retry_after = limiter.check("k", limit=3)
        assert allowed is False
        assert retry_after > 0.0

    def test_two_limiter_instances_share_state_via_redis(self, monkeypatch):
        # The whole point: unlike the in-memory dict (private per
        # instance/process), two independent RateLimiter objects pointed
        # at the same fake Redis genuinely share a budget — simulating
        # what two separate uvicorn worker processes would see.
        fake = _FakeRedis()
        monkeypatch.setattr("app.core.rate_limit.get_redis_client", lambda: fake)
        worker_a = RateLimiter(name="shared", window_seconds=60.0)
        worker_b = RateLimiter(name="shared", window_seconds=60.0)

        for _ in range(3):
            worker_a.check("k", limit=3)
        allowed, _ = worker_b.check("k", limit=3)
        assert allowed is False

    def test_different_limiter_names_have_independent_budgets(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr("app.core.rate_limit.get_redis_client", lambda: fake)
        general = RateLimiter(name="general", window_seconds=60.0)
        strict = RateLimiter(name="strict", window_seconds=60.0)

        for _ in range(3):
            general.check("k", limit=3)
        allowed_general, _ = general.check("k", limit=3)
        allowed_strict, _ = strict.check("k", limit=3)
        assert allowed_general is False
        assert allowed_strict is True

    def test_reset_clears_redis_keys(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr("app.core.rate_limit.get_redis_client", lambda: fake)
        limiter = RateLimiter(name="test", window_seconds=60.0)
        limiter.check("k", limit=1)
        limiter.check("k", limit=1)  # now over the limit

        limiter.reset()

        allowed, _ = limiter.check("k", limit=1)
        assert allowed is True

    def test_falls_back_to_in_memory_when_redis_is_unreachable(self, monkeypatch):
        monkeypatch.setattr("app.core.rate_limit.get_redis_client", lambda: _BrokenRedis())
        limiter = RateLimiter(name="test", window_seconds=60.0)

        # Still works — degrades to the in-memory limiter rather than
        # failing the request or raising.
        allowed, retry_after = limiter.check("k", limit=3)
        assert allowed is True
        assert retry_after == 0.0

"""Rate limiting — Redis-backed when Settings.redis_url is configured
(correct across multiple uvicorn workers), in-memory per-process
otherwise (documented limitation, Phase 13/14). See DEF.md § Phase 14,
"Multi-process rate limiting (post-roadmap)".

Fixed-window, not sliding/token-bucket in either backend — simple to
reason about and to test deterministically; the accepted trade-off is a
possible burst at a window boundary (up to ~2x the limit in the worst
case), fine for protecting a local single-operator tool from
runaway/abusive automated clients, not a claim of precise traffic shaping.
"""

import logging
import time
from dataclasses import dataclass, field

import redis

from app.core.config import get_settings
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

_STRICT_ROUTES = frozenset(
    {
        ("POST", "/api/v1/pipeline/run"),
        ("POST", "/api/v1/pipeline/reanalyze"),
    }
)


def _is_strict(method: str, path: str) -> bool:
    if (method, path) in _STRICT_ROUTES:
        return True
    # POST /api/v1/events/{source_type} — path has a variable segment.
    return method == "POST" and path.startswith("/api/v1/events/")


@dataclass
class RateLimiter:
    """`name` namespaces this limiter's keys in Redis (general vs. strict
    share one Redis instance) — irrelevant to the in-memory fallback,
    which already has its own separate dict per instance.
    """

    name: str
    window_seconds: float
    _windows: dict[str, tuple[float, int]] = field(default_factory=dict)

    def check(self, key: str, limit: int) -> tuple[bool, float]:
        """Returns (allowed, retry_after_seconds). Records the hit whether
        or not it's allowed, matching standard rate-limiter semantics (a
        client hammering past the limit doesn't get free retries). `limit`
        is passed in per call, read fresh from settings each time (not
        frozen at construction) — the same "no cached config" discipline
        get_current_user follows, and what lets tests override it via
        monkeypatching app.core.config.get_settings.
        """
        client = get_redis_client()
        if client is not None:
            result = self._check_redis(client, key, limit)
            if result is not None:
                return result
            # Redis configured but unreachable right now — a rate limiter
            # failing open (allowing the request) is the safer default
            # for an availability feature; this is not an auth boundary.
            logger.warning("Redis rate limiter unreachable, allowing request through")
        return self._check_in_memory(key, limit)

    def _check_redis(self, client: redis.Redis, key: str, limit: int) -> tuple[bool, float] | None:
        window_id = int(time.time() // self.window_seconds)
        redis_key = f"ratelimit:{self.name}:{key}:{window_id}"
        try:
            count = client.incr(redis_key)
            if count == 1:
                # Only the request that actually created the key sets its
                # expiry — a harmless small race if two requests both see
                # count==1 (both would set the same TTL anyway).
                client.expire(redis_key, int(self.window_seconds))
        except redis.RedisError:
            return None

        if count > limit:
            window_start = window_id * self.window_seconds
            retry_after = self.window_seconds - (time.time() - window_start)
            return False, max(retry_after, 0.0)
        return True, 0.0

    def _check_in_memory(self, key: str, limit: int) -> tuple[bool, float]:
        now = time.monotonic()
        window_start, count = self._windows.get(key, (now, 0))
        if now - window_start >= self.window_seconds:
            window_start, count = now, 0

        count += 1
        self._windows[key] = (window_start, count)

        if count > limit:
            retry_after = self.window_seconds - (now - window_start)
            return False, max(retry_after, 0.0)
        return True, 0.0

    def reset(self) -> None:
        """Test-only. Also clears this limiter's Redis keys, if any exist
        — a test run against a real Redis instance shouldn't leak state
        into the next one.
        """
        self._windows.clear()
        client = get_redis_client()
        if client is None:
            return
        try:
            keys = list(client.scan_iter(match=f"ratelimit:{self.name}:*"))
            if keys:
                client.delete(*keys)
        except redis.RedisError:
            pass


_general_limiter = RateLimiter(name="general", window_seconds=60.0)
_strict_limiter = RateLimiter(name="strict", window_seconds=60.0)


def check_rate_limit(method: str, path: str, client_key: str) -> tuple[bool, float]:
    """Only /api/v1/* is limited — health/metrics/docs stay exempt, same
    scope as get_current_user.
    """
    if not path.startswith("/api/v1/"):
        return True, 0.0
    settings = get_settings()
    if _is_strict(method, path):
        return _strict_limiter.check(client_key, settings.rate_limit_strict_per_minute)
    return _general_limiter.check(client_key, settings.rate_limit_general_per_minute)


def reset_rate_limiters() -> None:
    """Test-only: clears both limiters' state. See tests/conftest.py."""
    _general_limiter.reset()
    _strict_limiter.reset()

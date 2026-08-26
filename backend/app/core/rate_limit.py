"""In-memory, per-process rate limiting. See DEF.md § Phase 14.

Fixed-window, not sliding/token-bucket — simple to reason about and to
test deterministically; the accepted trade-off is a possible burst at a
window boundary (up to ~2x the limit in the worst case), fine for
protecting a local single-operator tool from runaway/abusive automated
clients, not a claim of precise traffic shaping.

In-memory only, single process — same documented limitation as Phase 13's
metrics registry: would under-count (i.e. under-limit) across multiple
worker processes without a shared store. Out of scope for this project's
documented single-`uvicorn`-process run mode.
"""

import time
from dataclasses import dataclass, field

from app.core.config import get_settings

_STRICT_ROUTES = frozenset(
    {
        ("POST", "/api/v1/pipeline/run"),
    }
)


def _is_strict(method: str, path: str) -> bool:
    if (method, path) in _STRICT_ROUTES:
        return True
    # POST /api/v1/events/{source_type} — path has a variable segment.
    return method == "POST" and path.startswith("/api/v1/events/")


@dataclass
class RateLimiter:
    window_seconds: float
    _windows: dict[str, tuple[float, int]] = field(default_factory=dict)

    def check(self, key: str, limit: int) -> tuple[bool, float]:
        """Returns (allowed, retry_after_seconds). Records the hit whether
        or not it's allowed, matching standard rate-limiter semantics (a
        client hammering past the limit doesn't get free retries). `limit`
        is passed in per call, read fresh from settings each time (not
        frozen at construction) — the same "no cached config" discipline
        require_auth follows, and what lets tests override it via
        monkeypatching app.core.config.get_settings.
        """
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
        self._windows.clear()


_general_limiter = RateLimiter(window_seconds=60.0)
_strict_limiter = RateLimiter(window_seconds=60.0)


def check_rate_limit(method: str, path: str, client_key: str) -> tuple[bool, float]:
    """Only /api/v1/* is limited — health/metrics/docs stay exempt, same
    scope as require_auth.
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

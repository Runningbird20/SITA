"""A single, lazily-created Redis client — None when Settings.redis_url is
unset (the default), so every caller has one obvious way to check "is a
shared store available" rather than each re-deriving it from settings.
See DEF.md § Phase 14, "Multi-process rate limiting (post-roadmap)".
"""

from functools import lru_cache

import redis

from app.core.config import get_settings


@lru_cache
def get_redis_client() -> "redis.Redis | None":
    url = get_settings().redis_url
    if not url:
        return None
    return redis.Redis.from_url(url, decode_responses=True)

from app.core.config import Settings
from app.core.redis_client import get_redis_client


class TestGetRedisClient:
    def test_returns_none_when_redis_url_is_unset(self, monkeypatch):
        get_redis_client.cache_clear()
        monkeypatch.setattr("app.core.redis_client.get_settings", lambda: Settings(redis_url=""))
        assert get_redis_client() is None
        get_redis_client.cache_clear()

    def test_returns_a_client_when_redis_url_is_set(self, monkeypatch):
        get_redis_client.cache_clear()
        monkeypatch.setattr(
            "app.core.redis_client.get_settings",
            lambda: Settings(redis_url="redis://localhost:6379/0"),
        )
        client = get_redis_client()
        assert client is not None
        get_redis_client.cache_clear()

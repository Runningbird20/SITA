import uuid

import httpx
import pytest

from app.notifications.base import NotificationPayload
from app.notifications.noop_notifier import NoOpNotifier
from app.notifications.registry import get_notifier
from app.notifications.webhook_notifier import WebhookNotifier

_PAYLOAD = NotificationPayload(
    incident_id=uuid.uuid4(), title="Test Incident", severity="critical", alert_count=3
)


class TestNoOpNotifier:
    def test_notify_never_raises(self):
        NoOpNotifier().notify(_PAYLOAD)  # no assertion needed — just must not raise


class TestWebhookNotifier:
    def test_posts_the_payload_as_json(self, monkeypatch):
        captured = {}

        def fake_post(url, json, timeout):
            captured["url"] = url
            captured["json"] = json
            return httpx.Response(200, request=httpx.Request("POST", url))

        monkeypatch.setattr(httpx, "post", fake_post)
        notifier = WebhookNotifier("https://example.test/hook")
        notifier.notify(_PAYLOAD)

        assert captured["url"] == "https://example.test/hook"
        assert captured["json"]["title"] == "Test Incident"
        assert captured["json"]["severity"] == "critical"
        assert captured["json"]["incident_id"] == str(_PAYLOAD.incident_id)

    def test_delivery_failure_does_not_raise(self, monkeypatch):
        def fake_post(url, json, timeout):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(httpx, "post", fake_post)
        notifier = WebhookNotifier("https://example.test/hook")
        notifier.notify(_PAYLOAD)  # must not raise

    def test_non_2xx_response_does_not_raise(self, monkeypatch):
        def fake_post(url, json, timeout):
            request = httpx.Request("POST", url)
            return httpx.Response(500, request=request)

        monkeypatch.setattr(httpx, "post", fake_post)
        WebhookNotifier("https://example.test/hook").notify(_PAYLOAD)


class TestGetNotifier:
    def test_defaults_to_noop(self, monkeypatch):
        from app.core.config import get_settings

        get_settings.cache_clear()
        monkeypatch.delenv("NOTIFIER", raising=False)
        monkeypatch.delenv("NOTIFIER_WEBHOOK_URL", raising=False)
        assert isinstance(get_notifier(), NoOpNotifier)
        get_settings.cache_clear()

    def test_webhook_requires_both_type_and_url(self, monkeypatch):
        from app.core.config import get_settings

        get_settings.cache_clear()
        monkeypatch.setenv("NOTIFIER", "webhook")
        monkeypatch.delenv("NOTIFIER_WEBHOOK_URL", raising=False)
        assert isinstance(get_notifier(), NoOpNotifier)
        get_settings.cache_clear()

    def test_webhook_selected_when_configured(self, monkeypatch):
        from app.core.config import get_settings

        get_settings.cache_clear()
        monkeypatch.setenv("NOTIFIER", "webhook")
        monkeypatch.setenv("NOTIFIER_WEBHOOK_URL", "https://example.test/hook")
        notifier = get_notifier()
        assert isinstance(notifier, WebhookNotifier)
        assert notifier.url == "https://example.test/hook"
        get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    yield
    from app.core.config import get_settings

    get_settings.cache_clear()

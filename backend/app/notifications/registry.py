"""Same "swapping backends requires no code changes elsewhere" shape as
app.llm.registry — callers use get_notifier() and never import a concrete
Notifier class directly.
"""

from app.core.config import get_settings
from app.notifications.base import Notifier
from app.notifications.noop_notifier import NoOpNotifier
from app.notifications.webhook_notifier import WebhookNotifier


def get_notifier() -> Notifier:
    settings = get_settings()
    if settings.notifier == "webhook" and settings.notifier_webhook_url:
        return WebhookNotifier(settings.notifier_webhook_url)
    return NoOpNotifier()

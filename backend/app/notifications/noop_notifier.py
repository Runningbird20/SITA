import logging

from app.notifications.base import NotificationPayload, Notifier

logger = logging.getLogger(__name__)


class NoOpNotifier(Notifier):
    """The default — zero network calls, matching MockProvider's own
    "runs with zero LLM network dependency by default" precedent. Still
    logs, so "a notification would have fired here" is visible without
    actually sending one.
    """

    name = "noop"

    def notify(self, payload: NotificationPayload) -> None:
        logger.info(
            "notification (noop, not delivered)",
            extra={
                "incident_id": str(payload.incident_id),
                "severity": payload.severity,
                "title": payload.title,
            },
        )

import logging
from dataclasses import asdict

import httpx

from app.notifications.base import NotificationPayload, Notifier

logger = logging.getLogger(__name__)


class WebhookNotifier(Notifier):
    """POSTs a JSON payload to a configured URL — works for a generic
    webhook receiver, Slack's incoming-webhooks format (the payload shape
    differs, but a Slack-side transform or a small relay can adapt it),
    or any HTTP endpoint. Deliberately not a vendor-specific SDK (Slack,
    PagerDuty, ...) — a webhook covers the general case without a new
    per-vendor dependency, matching this project's "no paid APIs" rule.
    """

    name = "webhook"

    def __init__(self, url: str, timeout_seconds: float = 5.0):
        self.url = url
        self.timeout_seconds = timeout_seconds

    def notify(self, payload: NotificationPayload) -> None:
        body = {**asdict(payload), "incident_id": str(payload.incident_id)}
        try:
            response = httpx.post(self.url, json=body, timeout=self.timeout_seconds)
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning(
                "notification delivery failed",
                extra={"incident_id": str(payload.incident_id), "url": self.url},
                exc_info=True,
            )

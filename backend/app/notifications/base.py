"""A swappable notification backend, parallel to app.llm.base.LLMProvider's
design — same "one abstract contract, multiple backends, a NoOp default so
the app makes zero network calls unless explicitly configured" shape. See
DEF.md § Phase 9, "Post-roadmap addition: incident notifications".
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationPayload:
    incident_id: uuid.UUID
    title: str
    severity: str
    alert_count: int


class Notifier(ABC):
    name: str

    @abstractmethod
    def notify(self, payload: NotificationPayload) -> None:
        """Must never raise — a notification-delivery failure is logged,
        not propagated, since it must never break the pipeline run that
        triggered it. Implementations are responsible for catching their
        own transport errors (see WebhookNotifier).
        """

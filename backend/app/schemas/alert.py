import uuid
from datetime import datetime

from app.models.enums import AlertStatus, Severity
from app.schemas.base import ORMBase


class AlertRead(ORMBase):
    id: uuid.UUID
    detection_id: uuid.UUID
    incident_id: uuid.UUID | None = None
    severity: Severity
    confidence: float
    status: AlertStatus
    rationale: str
    severity_factors: dict
    first_event_at: datetime
    last_event_at: datetime
    created_at: datetime
    updated_at: datetime

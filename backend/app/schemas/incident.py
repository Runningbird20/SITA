import uuid
from datetime import datetime

from app.models.enums import IncidentStatus, Severity
from app.schemas.base import ORMBase


class IncidentRead(ORMBase):
    id: uuid.UUID
    title: str
    status: IncidentStatus
    severity: Severity
    first_activity_at: datetime
    last_activity_at: datetime
    correlation_method: dict
    created_at: datetime
    updated_at: datetime

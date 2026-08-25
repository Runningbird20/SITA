import uuid
from datetime import datetime

from app.models.enums import DetectionCategory, Severity
from app.schemas.base import ORMBase


class DetectionRead(ORMBase):
    id: uuid.UUID
    rule_key: str
    name: str
    description: str
    category: DetectionCategory
    default_severity: Severity
    enabled: bool
    config: dict | None = None
    created_at: datetime

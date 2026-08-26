import uuid
from datetime import datetime

from app.models.enums import ExtractionSource, IOCType, ValidationStatus
from app.schemas.base import ORMBase


class IOCRead(ORMBase):
    id: uuid.UUID
    ioc_type: IOCType
    value: str
    extraction_source: ExtractionSource
    validation_status: ValidationStatus
    confidence: float
    first_seen: datetime
    last_seen: datetime
    created_at: datetime
    updated_at: datetime
    # Not from_attributes-derivable (IOC.alerts/.events are full ORM object
    # lists, not id lists) — the router builds these explicitly. Added for
    # Phase 10's IOC explorer, which TODO.md asks to "link back to source
    # alerts/events"; Phase 9 didn't anticipate the need.
    alert_ids: list[uuid.UUID]
    event_ids: list[uuid.UUID]

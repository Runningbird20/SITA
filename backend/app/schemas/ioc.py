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

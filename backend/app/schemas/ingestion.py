import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import SourceType


class ParsedEvent(BaseModel):
    """A raw record after adapter validation and normalization — ready to
    become a SecurityEvent row, not yet persisted.
    """

    source_type: SourceType
    occurred_at: datetime
    source_host: str
    raw_payload: dict
    normalized: dict


class IngestionReportError(BaseModel):
    index: int
    reason: str
    field: str | None = None


class IngestionReport(BaseModel):
    batch_id: uuid.UUID | None
    source_type: SourceType
    total: int
    accepted: int
    rejected: int
    errors: list[IngestionReportError]

import uuid
from datetime import datetime

from app.models.enums import SourceType
from app.schemas.base import ORMBase


class SecurityEventRead(ORMBase):
    id: uuid.UUID
    source_type: SourceType
    occurred_at: datetime
    ingested_at: datetime
    source_host: str | None = None
    raw_payload: dict
    normalized: dict
    ingestion_batch_id: uuid.UUID | None = None
    created_at: datetime

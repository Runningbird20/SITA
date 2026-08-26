import uuid
from datetime import datetime

from app.schemas.base import ORMBase


class AuditLogEntryRead(ORMBase):
    id: uuid.UUID
    user_id: uuid.UUID | None = None
    action: str
    resource_type: str | None = None
    resource_id: uuid.UUID | None = None
    detail: dict | None = None
    created_at: datetime

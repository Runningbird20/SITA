import uuid
from datetime import datetime

from app.models.enums import EntityType
from app.schemas.base import ORMBase


class EntityRead(ORMBase):
    id: uuid.UUID
    entity_type: EntityType
    identifier: str
    first_seen: datetime
    last_seen: datetime
    entity_metadata: dict | None = None
    created_at: datetime
    updated_at: datetime

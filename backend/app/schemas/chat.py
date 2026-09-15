import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import AnalysisValidationStatus, ChatRole
from app.schemas.base import ORMBase


class ChatMessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatMessageRead(ORMBase):
    id: uuid.UUID
    incident_id: uuid.UUID
    role: ChatRole
    content: str
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    validation_status: AnalysisValidationStatus | None = None
    confidence: float | None = None
    latency_ms: int | None = None
    created_at: datetime

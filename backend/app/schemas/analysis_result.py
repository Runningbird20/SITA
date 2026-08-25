import uuid
from datetime import datetime

from app.models.enums import AnalysisTaskType, AnalysisValidationStatus
from app.schemas.base import ORMBase


class AnalysisResultRead(ORMBase):
    id: uuid.UUID
    incident_id: uuid.UUID | None = None
    alert_id: uuid.UUID | None = None
    task_type: AnalysisTaskType
    provider: str
    model: str
    prompt_version: str
    raw_output: str
    parsed_output: dict | None = None
    validation_status: AnalysisValidationStatus
    confidence: float | None = None
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    created_at: datetime

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import PipelineJobStatus, PipelineJobType, PipelineStage


class PipelineJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_type: PipelineJobType
    status: PipelineJobStatus
    since: datetime | None
    current_stage: PipelineStage | None
    progress_current: int | None
    progress_total: int | None
    result: dict | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

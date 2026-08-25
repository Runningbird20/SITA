import uuid
from datetime import datetime

from app.models.enums import RecommendationPriority, RecommendationSource, RecommendationStatus
from app.schemas.base import ORMBase


class RecommendationRead(ORMBase):
    id: uuid.UUID
    incident_id: uuid.UUID | None = None
    alert_id: uuid.UUID | None = None
    source: RecommendationSource
    analysis_result_id: uuid.UUID | None = None
    text: str
    priority: RecommendationPriority
    status: RecommendationStatus
    created_at: datetime
    updated_at: datetime

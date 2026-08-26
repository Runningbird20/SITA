import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import FeedbackRating
from app.schemas.base import ORMBase


class AnalysisFeedbackRead(ORMBase):
    id: uuid.UUID
    analysis_result_id: uuid.UUID
    rating: FeedbackRating
    created_at: datetime
    updated_at: datetime


class AnalysisFeedbackCreate(BaseModel):
    rating: FeedbackRating

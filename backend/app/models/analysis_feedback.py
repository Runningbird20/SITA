import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import FeedbackRating

if TYPE_CHECKING:
    from app.models.analysis_result import AnalysisResult


class AnalysisFeedback(UUIDPKMixin, TimestampMixin, Base):
    """An analyst's thumbs up/down on one `AnalysisResult` — added
    post-roadmap (WHATNEXT.md 'AI quality' item) to start building a real
    dataset of which AI outputs an analyst actually trusted, as a
    precursor to any future fine-tuning or few-shot-example curation. One
    row per `AnalysisResult` (unique FK): casting a new vote updates the
    existing row rather than accumulating a history of votes — this is a
    live "is this useful" signal, not an audit trail.
    """

    __tablename__ = "analysis_feedback"

    analysis_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_results.id"), nullable=False, unique=True, index=True
    )
    rating: Mapped[FeedbackRating] = mapped_column(String(10), nullable=False)

    analysis_result: Mapped["AnalysisResult"] = relationship(back_populates="feedback")

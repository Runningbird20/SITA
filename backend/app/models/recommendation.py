import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import RecommendationPriority, RecommendationSource, RecommendationStatus

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.analysis_result import AnalysisResult
    from app.models.incident import Incident


class Recommendation(UUIDPKMixin, TimestampMixin, Base):
    """A suggested next step, from either the deterministic rule layer or
    the LLM — kept in one table but always labeled by `source`. `source`
    'llm' rows must carry an `analysis_result_id`; 'rule_based' rows never do.
    """

    __tablename__ = "recommendations"
    __table_args__ = (
        CheckConstraint(
            "(source = 'llm' AND analysis_result_id IS NOT NULL) "
            "OR (source = 'rule_based' AND analysis_result_id IS NULL)",
            name="ck_recommendation_llm_requires_analysis_result",
        ),
        Index("ix_recommendations_status", "status"),
    )

    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("incidents.id"), nullable=True, index=True
    )
    alert_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("alerts.id"), nullable=True, index=True
    )
    source: Mapped[RecommendationSource] = mapped_column(String(20), nullable=False)
    analysis_result_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_results.id"), nullable=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[RecommendationPriority] = mapped_column(String(20), nullable=False)
    status: Mapped[RecommendationStatus] = mapped_column(
        String(20), nullable=False, default=RecommendationStatus.OPEN
    )

    incident: Mapped["Incident | None"] = relationship(back_populates="recommendations")
    alert: Mapped["Alert | None"] = relationship(back_populates="recommendations")
    analysis_result: Mapped["AnalysisResult | None"] = relationship()

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.db.types import JSONVariant
from app.models.base import CreatedAtMixin, UUIDPKMixin
from app.models.enums import AnalysisTaskType, AnalysisValidationStatus

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.incident import Incident


class AnalysisResult(UUIDPKMixin, CreatedAtMixin, Base):
    """The envelope for every piece of LLM output — the single place 'AI
    said X' is recorded, so nothing downstream has to guess provenance.
    Scoped to exactly one of Incident or Alert.
    """

    __tablename__ = "analysis_results"
    __table_args__ = (
        CheckConstraint(
            "(incident_id IS NOT NULL AND alert_id IS NULL) "
            "OR (incident_id IS NULL AND alert_id IS NOT NULL)",
            name="ck_analysis_result_single_scope",
        ),
        Index("ix_analysis_results_task_type_created_at", "task_type", "created_at"),
    )

    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("incidents.id"), nullable=True, index=True
    )
    alert_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("alerts.id"), nullable=True, index=True
    )
    task_type: Mapped[AnalysisTaskType] = mapped_column(String(40), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(30), nullable=False)
    raw_output: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_output: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    validation_status: Mapped[AnalysisValidationStatus] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    incident: Mapped["Incident | None"] = relationship(back_populates="analysis_results")
    alert: Mapped["Alert | None"] = relationship(back_populates="analysis_results")

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.db.types import JSONVariant
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import IncidentStatus, Severity

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.analysis_result import AnalysisResult
    from app.models.recommendation import Recommendation


class Incident(UUIDPKMixin, TimestampMixin, Base):
    """A correlated group of one or more alerts representing a single
    security narrative. `correlation_method` records, per alert, which
    deterministic signals justified its membership.
    """

    __tablename__ = "incidents"
    __table_args__ = (Index("ix_incidents_status_severity", "status", "severity"),)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[IncidentStatus] = mapped_column(
        String(20), nullable=False, default=IncidentStatus.OPEN, index=True
    )
    severity: Mapped[Severity] = mapped_column(String(20), nullable=False, index=True)
    first_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    correlation_method: Mapped[dict] = mapped_column(JSONVariant, nullable=False)

    alerts: Mapped[list["Alert"]] = relationship(back_populates="incident")
    analysis_results: Mapped[list["AnalysisResult"]] = relationship(back_populates="incident")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="incident")

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.db.types import JSONVariant
from app.models.associations import alert_event, alert_ioc
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import AlertStatus, Severity

if TYPE_CHECKING:
    from app.models.analysis_result import AnalysisResult
    from app.models.associations import AlertEntity, AlertMitreMapping
    from app.models.detection import Detection
    from app.models.event import SecurityEvent
    from app.models.incident import Incident
    from app.models.ioc import IOC
    from app.models.recommendation import Recommendation


class Alert(UUIDPKMixin, TimestampMixin, Base):
    """One instance of a detection rule firing — always traceable back to
    its Detection and the SecurityEvents that triggered it.
    """

    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_detection_id_created_at", "detection_id", "created_at"),
        UniqueConstraint("fingerprint", name="uq_alerts_fingerprint"),
    )

    detection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("detections.id"), nullable=False, index=True
    )
    # SHA-256 hex digest of detection_id + sorted matched event IDs — makes
    # re-running detection over an overlapping window idempotent instead of
    # creating duplicate Alerts. See app/detection/base.py::
    # compute_alert_fingerprint and DEF.md § Phase 3 "Post-roadmap addition".
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("incidents.id"), nullable=True, index=True
    )
    severity: Mapped[Severity] = mapped_column(String(20), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[AlertStatus] = mapped_column(
        String(20), nullable=False, default=AlertStatus.NEW, index=True
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    severity_factors: Mapped[dict] = mapped_column(JSONVariant, nullable=False)
    first_event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    detection: Mapped["Detection"] = relationship(back_populates="alerts")
    incident: Mapped["Incident | None"] = relationship(back_populates="alerts")
    events: Mapped[list["SecurityEvent"]] = relationship(
        secondary=alert_event, back_populates="alerts"
    )
    iocs: Mapped[list["IOC"]] = relationship(secondary=alert_ioc, back_populates="alerts")
    entity_links: Mapped[list["AlertEntity"]] = relationship(
        back_populates="alert", cascade="all, delete-orphan"
    )
    mitre_mappings: Mapped[list["AlertMitreMapping"]] = relationship(
        back_populates="alert", cascade="all, delete-orphan"
    )
    analysis_results: Mapped[list["AnalysisResult"]] = relationship(back_populates="alert")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="alert")

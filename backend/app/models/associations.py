"""Many-to-many association tables.

Junctions with no extra data beyond the two foreign keys are plain Core
`Table` objects, wired via `relationship(secondary=...)`. Junctions that
carry their own attributes (e.g., a `role` or `source`) are mapped classes
instead, since `secondary=` has no attribute of its own to hold that data.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, String, Table, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import UUIDPKMixin
from app.models.enums import EntityRole, MitreMappingSource

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.analysis_result import AnalysisResult
    from app.models.entity import Entity
    from app.models.event import SecurityEvent
    from app.models.mitre import MITRETechnique

# --- Plain secondary tables (no extra columns) ---

alert_event = Table(
    "alert_event",
    Base.metadata,
    Column("alert_id", Uuid, ForeignKey("alerts.id"), primary_key=True),
    Column("event_id", Uuid, ForeignKey("security_events.id"), primary_key=True),
)

event_ioc = Table(
    "event_ioc",
    Base.metadata,
    Column("event_id", Uuid, ForeignKey("security_events.id"), primary_key=True),
    Column("ioc_id", Uuid, ForeignKey("iocs.id"), primary_key=True),
)

alert_ioc = Table(
    "alert_ioc",
    Base.metadata,
    Column("alert_id", Uuid, ForeignKey("alerts.id"), primary_key=True),
    Column("ioc_id", Uuid, ForeignKey("iocs.id"), primary_key=True),
)

detection_mitre_mapping = Table(
    "detection_mitre_mapping",
    Base.metadata,
    Column("detection_id", Uuid, ForeignKey("detections.id"), primary_key=True),
    Column("technique_id", Uuid, ForeignKey("mitre_techniques.id"), primary_key=True),
)


# --- Association objects (carry their own attributes) ---


class EventEntity(UUIDPKMixin, Base):
    """Links a SecurityEvent to an Entity it references, tagging the
    entity's role in that event (source / target / actor).
    """

    __tablename__ = "event_entity"

    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("security_events.id"), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), nullable=False)
    role: Mapped[EntityRole] = mapped_column(String(20), nullable=False)

    event: Mapped["SecurityEvent"] = relationship(back_populates="entity_links")
    entity: Mapped["Entity"] = relationship()


class AlertEntity(UUIDPKMixin, Base):
    """Links an Alert to an Entity involved in it, tagging its role."""

    __tablename__ = "alert_entity"

    alert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alerts.id"), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), nullable=False)
    role: Mapped[EntityRole] = mapped_column(String(20), nullable=False)

    alert: Mapped["Alert"] = relationship(back_populates="entity_links")
    entity: Mapped["Entity"] = relationship()


class AlertMitreMapping(UUIDPKMixin, Base):
    """Links an Alert to a MITRETechnique, tagging whether the mapping came
    from the deterministic rule definition or an LLM suggestion — a rule-
    sourced row never carries an `analysis_result_id`; an LLM-sourced row
    always does.
    """

    __tablename__ = "alert_mitre_mapping"

    alert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alerts.id"), nullable=False)
    technique_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mitre_techniques.id"), nullable=False
    )
    source: Mapped[MitreMappingSource] = mapped_column(String(20), nullable=False)
    analysis_result_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_results.id"), nullable=True
    )

    alert: Mapped["Alert"] = relationship(back_populates="mitre_mappings")
    technique: Mapped["MITRETechnique"] = relationship()
    analysis_result: Mapped["AnalysisResult | None"] = relationship()

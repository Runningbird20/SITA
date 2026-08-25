import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.db.types import JSONVariant
from app.models.associations import alert_event, event_ioc
from app.models.base import CreatedAtMixin, UUIDPKMixin
from app.models.enums import SourceType

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.associations import EventEntity
    from app.models.ioc import IOC


class SecurityEvent(UUIDPKMixin, CreatedAtMixin, Base):
    """The atomic, normalized unit of observation. Every ingested event
    becomes exactly one row, regardless of source type.
    """

    __tablename__ = "security_events"
    __table_args__ = (
        Index("ix_security_events_source_type_occurred_at", "source_type", "occurred_at"),
    )

    source_type: Mapped[SourceType] = mapped_column(String(20), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSONVariant, nullable=False)
    normalized: Mapped[dict] = mapped_column(JSONVariant, nullable=False)
    ingestion_batch_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)

    entity_links: Mapped[list["EventEntity"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["Alert"]] = relationship(secondary=alert_event, back_populates="events")
    iocs: Mapped[list["IOC"]] = relationship(secondary=event_ioc, back_populates="events")

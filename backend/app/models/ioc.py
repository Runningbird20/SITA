from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.associations import alert_ioc, event_ioc
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import ExtractionSource, IOCType, ValidationStatus

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.event import SecurityEvent


class IOC(UUIDPKMixin, TimestampMixin, Base):
    """A validated indicator of compromise, deduplicated across every event
    and alert that references it.
    """

    __tablename__ = "iocs"
    __table_args__ = (
        UniqueConstraint("ioc_type", "value", name="uq_ioc_type_value"),
        Index("ix_iocs_last_seen", "last_seen"),
    )

    ioc_type: Mapped[IOCType] = mapped_column(String(30), nullable=False, index=True)
    value: Mapped[str] = mapped_column(String(2048), nullable=False)
    extraction_source: Mapped[ExtractionSource] = mapped_column(String(20), nullable=False)
    validation_status: Mapped[ValidationStatus] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    events: Mapped[list["SecurityEvent"]] = relationship(secondary=event_ioc, back_populates="iocs")
    alerts: Mapped[list["Alert"]] = relationship(secondary=alert_ioc, back_populates="iocs")

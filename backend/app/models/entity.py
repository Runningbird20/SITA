from datetime import datetime

from sqlalchemy import DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.db.types import JSONVariant
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import EntityType


class Entity(UUIDPKMixin, TimestampMixin, Base):
    """A referenceable actor or asset (host, user, IP, domain) — the join
    point that makes correlation possible. Deduplicated by (entity_type,
    identifier).
    """

    __tablename__ = "entities"
    __table_args__ = (
        UniqueConstraint("entity_type", "identifier", name="uq_entity_type_identifier"),
        Index("ix_entities_last_seen", "last_seen"),
    )

    entity_type: Mapped[EntityType] = mapped_column(String(20), nullable=False, index=True)
    identifier: Mapped[str] = mapped_column(String(512), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    entity_metadata: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)

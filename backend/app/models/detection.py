from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.db.types import JSONVariant
from app.models.associations import detection_mitre_mapping
from app.models.base import CreatedAtMixin, UUIDPKMixin
from app.models.enums import DetectionCategory, Severity

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.mitre import MITRETechnique


class Detection(UUIDPKMixin, CreatedAtMixin, Base):
    """A deterministic rule *definition* — static metadata about a rule,
    distinct from any given firing (see Alert).
    """

    __tablename__ = "detections"

    rule_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[DetectionCategory] = mapped_column(String(20), nullable=False, index=True)
    default_severity: Mapped[Severity] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)

    alerts: Mapped[list["Alert"]] = relationship(back_populates="detection")
    mitre_techniques: Mapped[list["MITRETechnique"]] = relationship(
        secondary=detection_mitre_mapping, back_populates="detections"
    )

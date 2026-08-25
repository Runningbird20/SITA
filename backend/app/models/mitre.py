from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.associations import detection_mitre_mapping
from app.models.base import UUIDPKMixin

if TYPE_CHECKING:
    from app.models.detection import Detection


class MITRETechnique(UUIDPKMixin, Base):
    """Local, static representation of a relevant subset of MITRE ATT&CK —
    no runtime API dependency. Populated from a vendored local dataset.
    """

    __tablename__ = "mitre_techniques"

    technique_id: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    tactic: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(50), nullable=False)

    detections: Mapped[list["Detection"]] = relationship(
        secondary=detection_mitre_mapping, back_populates="mitre_techniques"
    )

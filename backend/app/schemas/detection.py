import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import DetectionCategory, Severity
from app.schemas.base import ORMBase
from app.schemas.mitre import MITRETechniqueRead


class DetectionConfigUpdate(BaseModel):
    """A partial merge into Detection.config, not a full replacement —
    e.g. {"failure_threshold": 12} only changes that one key, leaving
    every other existing config value (and any key not in this rule's
    default_config) untouched.
    """

    config: dict


class DetectionRead(ORMBase):
    id: uuid.UUID
    rule_key: str
    name: str
    description: str
    category: DetectionCategory
    default_severity: Severity
    enabled: bool
    config: dict | None = None
    created_at: datetime


class DetectionDetail(DetectionRead):
    mitre_techniques: list[MITRETechniqueRead]

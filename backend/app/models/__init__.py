"""Import every mapped class here so Base.metadata is fully populated
(for Alembic autogenerate) and all string-based relationship() references
resolve correctly (for SQLAlchemy's mapper configuration).
"""

from app.db.session import Base
from app.models.alert import Alert
from app.models.analysis_feedback import AnalysisFeedback
from app.models.analysis_result import AnalysisResult
from app.models.associations import (
    AlertEntity,
    AlertMitreMapping,
    EventEntity,
    alert_event,
    alert_ioc,
    detection_mitre_mapping,
    event_ioc,
)
from app.models.detection import Detection
from app.models.entity import Entity
from app.models.event import SecurityEvent
from app.models.incident import Incident
from app.models.ioc import IOC
from app.models.mitre import MITRETechnique
from app.models.recommendation import Recommendation

__all__ = [
    "Base",
    "Alert",
    "AlertEntity",
    "AlertMitreMapping",
    "AnalysisFeedback",
    "AnalysisResult",
    "Detection",
    "Entity",
    "EventEntity",
    "IOC",
    "Incident",
    "MITRETechnique",
    "Recommendation",
    "SecurityEvent",
    "alert_event",
    "alert_ioc",
    "detection_mitre_mapping",
    "event_ioc",
]

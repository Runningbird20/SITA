import uuid
from datetime import datetime

from app.models.enums import IncidentStatus, Severity
from app.schemas.alert import AlertRead
from app.schemas.analysis_result import AnalysisResultRead
from app.schemas.base import ORMBase
from app.schemas.ioc import IOCRead
from app.schemas.mitre import IncidentTechniqueEntryOut
from app.schemas.recommendation import RecommendationRead


class IncidentRead(ORMBase):
    id: uuid.UUID
    title: str
    status: IncidentStatus
    severity: Severity
    first_activity_at: datetime
    last_activity_at: datetime
    correlation_method: dict
    created_at: datetime
    updated_at: datetime


class IncidentDetail(IncidentRead):
    """GET /incidents/{id} — IncidentRead plus every related object a
    caller would otherwise need N additional requests to assemble. See
    DEF.md § Phase 9.
    """

    alerts: list[AlertRead]
    iocs: list[IOCRead]
    analysis_results: list[AnalysisResultRead]
    recommendations: list[RecommendationRead]
    mitre_techniques: list[IncidentTechniqueEntryOut]

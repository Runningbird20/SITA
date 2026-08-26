import uuid
from datetime import datetime

from app.models.enums import IncidentStatus, Severity
from app.schemas.alert import AlertRead
from app.schemas.analysis_result import AnalysisResultRead
from app.schemas.base import ORMBase
from app.schemas.entity import EntityRead
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
    # Not on the Incident model itself — computed by the list/get endpoints
    # (an aggregate query for the list, len(alerts) for the detail view).
    # Added for Phase 10's incident list view, which TODO.md's own task
    # asks to show "alert count"; Phase 9 didn't anticipate the need. See
    # DEF.md § Phase 9's endpoint reference for the note on this addition.
    alert_count: int


class IncidentDetail(IncidentRead):
    """GET /incidents/{id} — IncidentRead plus every related object a
    caller would otherwise need N additional requests to assemble. See
    DEF.md § Phase 9.
    """

    alerts: list[AlertRead]
    iocs: list[IOCRead]
    entities: list[EntityRead]
    analysis_results: list[AnalysisResultRead]
    recommendations: list[RecommendationRead]
    mitre_techniques: list[IncidentTechniqueEntryOut]

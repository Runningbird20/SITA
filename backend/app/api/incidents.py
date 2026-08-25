import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import PageParams, apply_sort, pagination_params
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.mitre.rollup import incident_technique_rollup
from app.models.enums import IncidentStatus, Severity
from app.models.incident import Incident
from app.schemas.incident import IncidentDetail, IncidentRead
from app.schemas.mitre import IncidentTechniqueEntryOut, TechniqueEvidenceOut
from app.schemas.pagination import Page

router = APIRouter(prefix=f"{get_settings().api_v1_prefix}/incidents", tags=["incidents"])

_SORTABLE = {
    "created_at": Incident.created_at,
    "first_activity_at": Incident.first_activity_at,
    "last_activity_at": Incident.last_activity_at,
}


def _get_incident_or_404(db: Session, incident_id: uuid.UUID) -> Incident:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise NotFoundError("Incident", incident_id)
    return incident


def _rollup_out(incident: Incident) -> list[IncidentTechniqueEntryOut]:
    return [
        IncidentTechniqueEntryOut(
            technique_id=entry.technique_id,
            name=entry.name,
            tactic=entry.tactic,
            evidence=[
                TechniqueEvidenceOut(
                    alert_id=e.alert_id,
                    source=e.source,
                    analysis_result_id=e.analysis_result_id,
                    confidence=e.confidence,
                )
                for e in entry.evidence
            ],
            sources=sorted(entry.sources),
        )
        for entry in incident_technique_rollup(incident)
    ]


@router.get("", response_model=Page[IncidentRead])
def list_incidents(
    status: IncidentStatus | None = Query(None),
    severity: Severity | None = Query(None),
    sort: str | None = Query(None, description="created_at | first_activity_at | last_activity_at"),
    page: PageParams = Depends(pagination_params),
    db: Session = Depends(get_db),
) -> Page[IncidentRead]:
    """List/filter incidents by status or severity."""
    stmt = select(Incident)
    if status is not None:
        stmt = stmt.where(Incident.status == status)
    if severity is not None:
        stmt = stmt.where(Incident.severity == severity)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = apply_sort(stmt, sort, _SORTABLE, default="-last_activity_at")
    items = db.scalars(stmt.limit(page.limit).offset(page.offset)).all()
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/{incident_id}", response_model=IncidentDetail)
def get_incident(incident_id: uuid.UUID, db: Session = Depends(get_db)) -> IncidentDetail:
    """Get one incident with its alerts, deduplicated IOCs (rolled up
    across those alerts), AI analyses, recommendations, and MITRE
    technique rollup.
    """
    incident = _get_incident_or_404(db, incident_id)

    iocs = {}
    for alert in incident.alerts:
        for ioc in alert.iocs:
            iocs[ioc.id] = ioc

    return IncidentDetail(
        id=incident.id,
        title=incident.title,
        status=incident.status,
        severity=incident.severity,
        first_activity_at=incident.first_activity_at,
        last_activity_at=incident.last_activity_at,
        correlation_method=incident.correlation_method,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        alerts=list(incident.alerts),
        iocs=list(iocs.values()),
        analysis_results=list(incident.analysis_results),
        recommendations=list(incident.recommendations),
        mitre_techniques=_rollup_out(incident),
    )


@router.get("/{incident_id}/mitre-techniques", response_model=list[IncidentTechniqueEntryOut])
def get_incident_mitre_techniques(
    incident_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[IncidentTechniqueEntryOut]:
    """Standalone MITRE technique rollup for one incident — same data as
    the nested field on GET /incidents/{id}, for a caller that only wants this.
    """
    incident = _get_incident_or_404(db, incident_id)
    return _rollup_out(incident)

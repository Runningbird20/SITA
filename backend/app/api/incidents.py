import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.converters import to_ioc_read
from app.api.deps import PageParams, apply_sort, pagination_params
from app.auth.deps import CurrentUser, get_current_user
from app.chat.service import ask_incident_question
from app.core.audit import record_audit
from app.core.config import get_settings
from app.core.exceptions import InvalidQueryParameterError, NotFoundError
from app.db.session import get_db
from app.export.csv_export import export_incident_csv
from app.export.pdf_export import export_incident_pdf
from app.mitre.rollup import incident_technique_rollup
from app.models.alert import Alert
from app.models.analysis_result import AnalysisResult
from app.models.chat_message import ChatMessage
from app.models.enums import AnalysisTaskType, IncidentStatus, Severity
from app.models.incident import Incident
from app.schemas.chat import ChatMessageCreate, ChatMessageRead
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


def _latest_analysis_results(incident: Incident) -> list[AnalysisResult]:
    """One result per task_type — the most recent, not every historical
    attempt. `run_triage(..., force=True)` adds a new row rather than
    replacing an old one (by design, for auditability — see DEF.md §
    Phase 7), so without this an incident's AI panel would show a stale
    (sometimes invalid) result from an earlier run ahead of a later,
    valid one, in whatever order the DB happens to return them. Bugfix
    found by actually looking at a real incident with more than one
    triage run behind it, not assumed.
    """
    latest: dict[AnalysisTaskType, AnalysisResult] = {}
    for result in incident.analysis_results:
        current = latest.get(result.task_type)
        if current is None or result.created_at >= current.created_at:
            latest[result.task_type] = result
    return sorted(latest.values(), key=lambda r: r.created_at)


def _to_incident_read(incident: Incident, alert_count: int) -> IncidentRead:
    return IncidentRead(
        id=incident.id,
        title=incident.title,
        status=incident.status,
        severity=incident.severity,
        first_activity_at=incident.first_activity_at,
        last_activity_at=incident.last_activity_at,
        correlation_method=incident.correlation_method,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        alert_count=alert_count,
    )


@router.get("", response_model=Page[IncidentRead])
def list_incidents(
    status: IncidentStatus | None = Query(None),
    severity: Severity | None = Query(None),
    sort: str | None = Query(None, description="created_at | first_activity_at | last_activity_at"),
    page: PageParams = Depends(pagination_params),
    db: Session = Depends(get_db),
) -> Page[IncidentRead]:
    """List/filter incidents by status or severity."""
    # alert_count via a pre-aggregated subquery, not len(incident.alerts)
    # per row — avoids N+1 lazy-loads across a page of incidents.
    counts = (
        select(Alert.incident_id, func.count(Alert.id).label("alert_count"))
        .group_by(Alert.incident_id)
        .subquery()
    )
    stmt = select(Incident, func.coalesce(counts.c.alert_count, 0)).outerjoin(
        counts, counts.c.incident_id == Incident.id
    )
    if status is not None:
        stmt = stmt.where(Incident.status == status)
    if severity is not None:
        stmt = stmt.where(Incident.severity == severity)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = apply_sort(stmt, sort, _SORTABLE, default="-last_activity_at")
    rows = db.execute(stmt.limit(page.limit).offset(page.offset)).all()
    items = [_to_incident_read(incident, count) for incident, count in rows]
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/{incident_id}", response_model=IncidentDetail)
def get_incident(incident_id: uuid.UUID, db: Session = Depends(get_db)) -> IncidentDetail:
    """Get one incident with its alerts, deduplicated IOCs and entities
    (rolled up across those alerts), AI analyses, recommendations, and
    MITRE technique rollup.
    """
    incident = _get_incident_or_404(db, incident_id)

    iocs = {}
    entities = {}
    for alert in incident.alerts:
        for ioc in alert.iocs:
            iocs[ioc.id] = ioc
        for link in alert.entity_links:
            entities[link.entity.id] = link.entity

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
        alert_count=len(incident.alerts),
        alerts=list(incident.alerts),
        iocs=[to_ioc_read(ioc) for ioc in iocs.values()],
        entities=list(entities.values()),
        analysis_results=_latest_analysis_results(incident),
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


@router.get("/{incident_id}/export")
def export_incident(
    incident_id: uuid.UUID,
    format: str = Query("csv", description="csv | pdf"),
    db: Session = Depends(get_db),
) -> Response:
    """A downloadable incident report — resolves WHATNEXT.md's "Export"
    item. See DEF.md § Phase 9, "Post-roadmap addition: incident export
    (CSV/PDF)". Built from the real ORM Incident, not IncidentDetail —
    the CSV/PDF builders want the detection *name*, not just its id.
    """
    incident = _get_incident_or_404(db, incident_id)

    if format == "csv":
        content = export_incident_csv(incident)
        media_type = "text/csv"
        filename = f"incident-{incident_id}.csv"
    elif format == "pdf":
        content = export_incident_pdf(incident)
        media_type = "application/pdf"
        filename = f"incident-{incident_id}.pdf"
    else:
        raise InvalidQueryParameterError(f"format must be 'csv' or 'pdf', got {format!r}")

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{incident_id}/chat", response_model=list[ChatMessageRead])
def get_incident_chat(incident_id: uuid.UUID, db: Session = Depends(get_db)) -> list[ChatMessage]:
    """Full conversation history for this incident, oldest first —
    resolves WHATNEXT.md's "Bigger bets" item, "a conversational interface
    with an incident". See DEF.md § Phase 7, "Post-roadmap addition: a
    conversational interface with an incident".
    """
    incident = _get_incident_or_404(db, incident_id)
    return incident.chat_messages


@router.post("/{incident_id}/chat", response_model=ChatMessageRead)
def post_incident_chat(
    incident_id: uuid.UUID,
    body: ChatMessageCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ChatMessage:
    """Asks a free-form follow-up question about this incident, grounded
    in the same context block the six fixed triage tasks use, plus this
    thread's own prior turns. Returns only the assistant's reply — the
    question the caller just sent is already known to them; fetch
    GET .../chat for the full thread including it. Rate-limited under the
    strict tier (same as pipeline runs and event ingestion), since each
    call is a real LLM invocation, not a cheap read.
    """
    incident = _get_incident_or_404(db, incident_id)
    reply = ask_incident_question(db, incident, body.message)
    record_audit(
        db,
        current_user,
        action="incident.chat",
        resource_type="incident",
        resource_id=incident_id,
        detail={"question": body.message},
    )
    db.commit()
    db.refresh(reply)
    return reply

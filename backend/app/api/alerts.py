import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import PageParams, apply_sort, pagination_params
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.alert import Alert
from app.models.detection import Detection
from app.models.enums import AlertStatus, Severity
from app.schemas.alert import AlertRead
from app.schemas.mitre import AlertMitreMappingRead
from app.schemas.pagination import Page

router = APIRouter(prefix=f"{get_settings().api_v1_prefix}/alerts", tags=["alerts"])

_SORTABLE = {
    "created_at": Alert.created_at,
    "first_event_at": Alert.first_event_at,
    "last_event_at": Alert.last_event_at,
    "confidence": Alert.confidence,
}


@router.get("", response_model=Page[AlertRead])
def list_alerts(
    severity: Severity | None = Query(None),
    status: AlertStatus | None = Query(None),
    rule_key: str | None = Query(None, description="Detection.rule_key"),
    incident_id: uuid.UUID | None = Query(None),
    sort: str | None = Query(
        None, description="created_at | first_event_at | last_event_at | confidence"
    ),
    page: PageParams = Depends(pagination_params),
    db: Session = Depends(get_db),
) -> Page[AlertRead]:
    """List/filter alerts by severity, status, rule, or incident."""
    stmt = select(Alert)
    if rule_key is not None:
        stmt = stmt.join(Detection, Alert.detection_id == Detection.id).where(
            Detection.rule_key == rule_key
        )
    if severity is not None:
        stmt = stmt.where(Alert.severity == severity)
    if status is not None:
        stmt = stmt.where(Alert.status == status)
    if incident_id is not None:
        stmt = stmt.where(Alert.incident_id == incident_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = apply_sort(stmt, sort, _SORTABLE, default="-first_event_at")
    items = db.scalars(stmt.limit(page.limit).offset(page.offset)).all()
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/{alert_id}", response_model=AlertRead)
def get_alert(alert_id: uuid.UUID, db: Session = Depends(get_db)) -> Alert:
    """Get one alert by id."""
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise NotFoundError("Alert", alert_id)
    return alert


@router.get("/{alert_id}/mitre-techniques", response_model=list[AlertMitreMappingRead])
def get_alert_mitre_techniques(alert_id: uuid.UUID, db: Session = Depends(get_db)) -> list:
    """This alert's own rule- and/or LLM-sourced MITRE technique mappings."""
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise NotFoundError("Alert", alert_id)
    return alert.mitre_mappings

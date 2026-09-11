import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import PageParams, apply_sort, pagination_params
from app.auth.deps import CurrentUser, require_admin
from app.core.audit import record_audit
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.detection import Detection
from app.models.enums import DetectionCategory
from app.rule_tuning.analyzer import compute_tuning_suggestions
from app.schemas.detection import DetectionConfigUpdate, DetectionDetail, DetectionRead
from app.schemas.pagination import Page
from app.schemas.rule_tuning import TuningSuggestionRead

router = APIRouter(prefix=f"{get_settings().api_v1_prefix}/detections", tags=["detections"])

_SORTABLE = {
    "name": Detection.name,
    "created_at": Detection.created_at,
}


@router.get("", response_model=Page[DetectionRead])
def list_detections(
    category: DetectionCategory | None = Query(None),
    enabled: bool | None = Query(None),
    sort: str | None = Query(None, description="name | created_at"),
    page: PageParams = Depends(pagination_params),
    db: Session = Depends(get_db),
) -> Page[DetectionRead]:
    """List/filter detection rule definitions."""
    stmt = select(Detection)
    if category is not None:
        stmt = stmt.where(Detection.category == category)
    if enabled is not None:
        stmt = stmt.where(Detection.enabled == enabled)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = apply_sort(stmt, sort, _SORTABLE, default="name")
    items = db.scalars(stmt.limit(page.limit).offset(page.offset)).all()
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/tuning-suggestions", response_model=list[TuningSuggestionRead])
def get_tuning_suggestions(db: Session = Depends(get_db)) -> list[TuningSuggestionRead]:
    """Deterministic, advisory-only rule-tuning suggestions computed from
    analyst false-positive feedback (PUT /alerts/{id}/status) — resolves
    WHATNEXT.md's "Analyst feedback closing the loop into rule tuning"
    item. No LLM involved; nothing here writes to Detection.config on its
    own — see PATCH /detections/{id}/config to apply one. Registered
    *before* GET /{detection_id} below: a static "tuning-suggestions"
    segment sharing a prefix with a path-param route would otherwise be
    shadowed by it (the same FastAPI route-ordering gotcha already
    documented in app/live_updates/stream.py). See DEF.md § Phase 3,
    "Post-roadmap addition: rule tuning suggestions from analyst
    feedback".
    """
    return [TuningSuggestionRead(**s.as_dict()) for s in compute_tuning_suggestions(db)]


@router.get("/{detection_id}", response_model=DetectionDetail)
def get_detection(detection_id: uuid.UUID, db: Session = Depends(get_db)) -> Detection:
    """Get one detection rule definition, with its declared MITRE techniques."""
    detection = db.get(Detection, detection_id)
    if detection is None:
        raise NotFoundError("Detection", detection_id)
    return detection


@router.patch("/{detection_id}/config", response_model=DetectionRead)
def update_detection_config(
    detection_id: uuid.UUID,
    body: DetectionConfigUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser | None = Depends(require_admin),
) -> Detection:
    """Merge new values into a Detection's config — e.g. applying a
    tuning suggestion above, or any other manual adjustment. A partial
    merge, not a full replacement: keys not present in `body.config` are
    left untouched. Admin-only, since this changes real detection
    behavior for every future pipeline run, not just this analyst's own
    view of one alert. See DEF.md § Phase 3, "Post-roadmap addition: rule
    tuning suggestions from analyst feedback".
    """
    detection = db.get(Detection, detection_id)
    if detection is None:
        raise NotFoundError("Detection", detection_id)

    merged = {**(detection.config or {}), **body.config}
    detection.config = merged

    record_audit(
        db,
        current_user,
        action="detection.update_config",
        resource_type="detection",
        resource_id=detection_id,
        detail={"config": body.config},
    )
    db.commit()
    db.refresh(detection)
    return detection

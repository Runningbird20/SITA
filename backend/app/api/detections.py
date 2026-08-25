import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import PageParams, apply_sort, pagination_params
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.detection import Detection
from app.models.enums import DetectionCategory
from app.schemas.detection import DetectionDetail, DetectionRead
from app.schemas.pagination import Page

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


@router.get("/{detection_id}", response_model=DetectionDetail)
def get_detection(detection_id: uuid.UUID, db: Session = Depends(get_db)) -> Detection:
    """Get one detection rule definition, with its declared MITRE techniques."""
    detection = db.get(Detection, detection_id)
    if detection is None:
        raise NotFoundError("Detection", detection_id)
    return detection

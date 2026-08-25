import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import PageParams, apply_sort, pagination_params
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.enums import RecommendationPriority, RecommendationSource, RecommendationStatus
from app.models.recommendation import Recommendation
from app.schemas.pagination import Page
from app.schemas.recommendation import RecommendationRead

router = APIRouter(
    prefix=f"{get_settings().api_v1_prefix}/recommendations", tags=["recommendations"]
)

_SORTABLE = {
    "created_at": Recommendation.created_at,
    "updated_at": Recommendation.updated_at,
}


@router.get("", response_model=Page[RecommendationRead])
def list_recommendations(
    incident_id: uuid.UUID | None = Query(None),
    alert_id: uuid.UUID | None = Query(None),
    status: RecommendationStatus | None = Query(None),
    source: RecommendationSource | None = Query(None),
    priority: RecommendationPriority | None = Query(None),
    sort: str | None = Query(None, description="created_at | updated_at"),
    page: PageParams = Depends(pagination_params),
    db: Session = Depends(get_db),
) -> Page[RecommendationRead]:
    """List/filter recommendations."""
    stmt = select(Recommendation)
    if incident_id is not None:
        stmt = stmt.where(Recommendation.incident_id == incident_id)
    if alert_id is not None:
        stmt = stmt.where(Recommendation.alert_id == alert_id)
    if status is not None:
        stmt = stmt.where(Recommendation.status == status)
    if source is not None:
        stmt = stmt.where(Recommendation.source == source)
    if priority is not None:
        stmt = stmt.where(Recommendation.priority == priority)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = apply_sort(stmt, sort, _SORTABLE, default="-created_at")
    items = db.scalars(stmt.limit(page.limit).offset(page.offset)).all()
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/{recommendation_id}", response_model=RecommendationRead)
def get_recommendation(
    recommendation_id: uuid.UUID, db: Session = Depends(get_db)
) -> Recommendation:
    """Get one recommendation by id."""
    recommendation = db.get(Recommendation, recommendation_id)
    if recommendation is None:
        raise NotFoundError("Recommendation", recommendation_id)
    return recommendation

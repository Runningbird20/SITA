import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import PageParams, apply_sort, pagination_params
from app.core.config import get_settings
from app.core.exceptions import InvalidQueryParameterError, NotFoundError
from app.db.session import get_db
from app.models.analysis_result import AnalysisResult
from app.models.enums import AnalysisTaskType
from app.schemas.analysis_result import AnalysisResultRead
from app.schemas.pagination import Page

router = APIRouter(
    prefix=f"{get_settings().api_v1_prefix}/analysis-results", tags=["analysis-results"]
)

_SORTABLE = {"created_at": AnalysisResult.created_at}


@router.get("", response_model=Page[AnalysisResultRead])
def list_analysis_results(
    incident_id: uuid.UUID | None = Query(None),
    alert_id: uuid.UUID | None = Query(None),
    task_type: AnalysisTaskType | None = Query(None),
    sort: str | None = Query(None, description="created_at"),
    page: PageParams = Depends(pagination_params),
    db: Session = Depends(get_db),
) -> Page[AnalysisResultRead]:
    """List AI analyses — must be scoped to exactly one of incident_id/alert_id."""
    if (incident_id is None) == (alert_id is None):
        raise InvalidQueryParameterError("exactly one of incident_id or alert_id is required")

    stmt = select(AnalysisResult)
    if incident_id is not None:
        stmt = stmt.where(AnalysisResult.incident_id == incident_id)
    else:
        stmt = stmt.where(AnalysisResult.alert_id == alert_id)
    if task_type is not None:
        stmt = stmt.where(AnalysisResult.task_type == task_type)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = apply_sort(stmt, sort, _SORTABLE, default="-created_at")
    items = db.scalars(stmt.limit(page.limit).offset(page.offset)).all()
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/{analysis_result_id}", response_model=AnalysisResultRead)
def get_analysis_result(
    analysis_result_id: uuid.UUID, db: Session = Depends(get_db)
) -> AnalysisResult:
    """Get one AI analysis result by id."""
    result = db.get(AnalysisResult, analysis_result_id)
    if result is None:
        raise NotFoundError("AnalysisResult", analysis_result_id)
    return result

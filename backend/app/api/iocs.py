import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import PageParams, apply_sort, pagination_params
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.enums import IOCType, ValidationStatus
from app.models.ioc import IOC
from app.schemas.ioc import IOCRead
from app.schemas.pagination import Page

router = APIRouter(prefix=f"{get_settings().api_v1_prefix}/iocs", tags=["iocs"])

_SORTABLE = {
    "first_seen": IOC.first_seen,
    "last_seen": IOC.last_seen,
    "confidence": IOC.confidence,
    "created_at": IOC.created_at,
}


@router.get("", response_model=Page[IOCRead])
def list_iocs(
    ioc_type: IOCType | None = Query(None),
    validation_status: ValidationStatus | None = Query(None),
    min_confidence: float | None = Query(None, ge=0.0, le=1.0),
    sort: str | None = Query(None, description="first_seen | last_seen | confidence | created_at"),
    page: PageParams = Depends(pagination_params),
    db: Session = Depends(get_db),
) -> Page[IOCRead]:
    """List/filter IOCs by type, validation status, or minimum confidence."""
    stmt = select(IOC)
    if ioc_type is not None:
        stmt = stmt.where(IOC.ioc_type == ioc_type)
    if validation_status is not None:
        stmt = stmt.where(IOC.validation_status == validation_status)
    if min_confidence is not None:
        stmt = stmt.where(IOC.confidence >= min_confidence)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = apply_sort(stmt, sort, _SORTABLE, default="-last_seen")
    items = db.scalars(stmt.limit(page.limit).offset(page.offset)).all()
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/{ioc_id}", response_model=IOCRead)
def get_ioc(ioc_id: uuid.UUID, db: Session = Depends(get_db)) -> IOC:
    """Get one IOC by id."""
    ioc = db.get(IOC, ioc_id)
    if ioc is None:
        raise NotFoundError("IOC", ioc_id)
    return ioc

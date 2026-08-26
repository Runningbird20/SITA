import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.converters import to_ioc_read
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
    search: str | None = Query(None, description="Substring match against value"),
    sort: str | None = Query(None, description="first_seen | last_seen | confidence | created_at"),
    page: PageParams = Depends(pagination_params),
    db: Session = Depends(get_db),
) -> Page[IOCRead]:
    """List/filter/search IOCs by type, validation status, minimum
    confidence, or a substring of their value.
    """
    stmt = select(IOC)
    if ioc_type is not None:
        stmt = stmt.where(IOC.ioc_type == ioc_type)
    if validation_status is not None:
        stmt = stmt.where(IOC.validation_status == validation_status)
    if min_confidence is not None:
        stmt = stmt.where(IOC.confidence >= min_confidence)
    if search:
        stmt = stmt.where(IOC.value.ilike(f"%{search}%"))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = apply_sort(stmt, sort, _SORTABLE, default="-last_seen")
    iocs = db.scalars(stmt.limit(page.limit).offset(page.offset)).all()
    items = [to_ioc_read(ioc) for ioc in iocs]
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/{ioc_id}", response_model=IOCRead)
def get_ioc(ioc_id: uuid.UUID, db: Session = Depends(get_db)) -> IOCRead:
    """Get one IOC by id, with the ids of the alerts/events it's linked to."""
    ioc = db.get(IOC, ioc_id)
    if ioc is None:
        raise NotFoundError("IOC", ioc_id)
    return to_ioc_read(ioc)

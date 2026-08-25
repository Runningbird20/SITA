import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import PageParams, apply_sort, pagination_params
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.ingestion.service import ingest_records
from app.models.enums import SourceType
from app.models.event import SecurityEvent
from app.schemas.event import SecurityEventRead
from app.schemas.ingestion import IngestionReport
from app.schemas.pagination import Page

router = APIRouter(prefix=f"{get_settings().api_v1_prefix}/events", tags=["events"])

_SORTABLE = {
    "occurred_at": SecurityEvent.occurred_at,
    "ingested_at": SecurityEvent.ingested_at,
    "created_at": SecurityEvent.created_at,
}


@router.get("", response_model=Page[SecurityEventRead])
def list_events(
    source_type: SourceType | None = Query(None),
    since: datetime | None = Query(None, description="occurred_at >= since"),
    until: datetime | None = Query(None, description="occurred_at <= until"),
    sort: str | None = Query(
        None, description="occurred_at | ingested_at | created_at, -prefix for desc"
    ),
    page: PageParams = Depends(pagination_params),
    db: Session = Depends(get_db),
) -> Page[SecurityEventRead]:
    """List/filter security events."""
    stmt = select(SecurityEvent)
    if source_type is not None:
        stmt = stmt.where(SecurityEvent.source_type == source_type)
    if since is not None:
        stmt = stmt.where(SecurityEvent.occurred_at >= since)
    if until is not None:
        stmt = stmt.where(SecurityEvent.occurred_at <= until)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = apply_sort(stmt, sort, _SORTABLE, default="-occurred_at")
    items = db.scalars(stmt.limit(page.limit).offset(page.offset)).all()
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/{event_id}", response_model=SecurityEventRead)
def get_event(event_id: uuid.UUID, db: Session = Depends(get_db)) -> SecurityEvent:
    """Get one security event by id."""
    event = db.get(SecurityEvent, event_id)
    if event is None:
        raise NotFoundError("SecurityEvent", event_id)
    return event


@router.post("/{source_type}", response_model=IngestionReport, status_code=201)
def ingest_events(
    source_type: SourceType,
    payload: dict[str, Any] | list[dict[str, Any]] = Body(...),
    db: Session = Depends(get_db),
) -> IngestionReport:
    """Ingest one or more raw events of a single source type. Narrow,
    write-only endpoint — no ingestion_batch_id is assigned (that's
    reserved for the batch-file-import path). See DEF.md § Phase 2 §4.
    """
    records = payload if isinstance(payload, list) else [payload]
    report = ingest_records(db=db, source_type=source_type, raw_records=records, batch_id=None)
    db.commit()
    return report

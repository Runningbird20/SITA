from typing import Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.ingestion.service import ingest_records
from app.models.enums import SourceType
from app.schemas.ingestion import IngestionReport

router = APIRouter(prefix=f"{get_settings().api_v1_prefix}/events", tags=["events"])


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

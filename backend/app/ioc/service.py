from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import as_aware_utc
from app.ioc.base import ExtractedIOC
from app.models.event import SecurityEvent
from app.models.ioc import IOC


def upsert_ioc(db: Session, candidate: ExtractedIOC, seen_at: datetime) -> tuple[IOC, bool]:
    """Insert or update an IOC row by (ioc_type, value). Returns (ioc, created)."""
    existing = db.scalars(
        select(IOC).where(IOC.ioc_type == candidate.ioc_type, IOC.value == candidate.value)
    ).one_or_none()

    if existing is None:
        ioc = IOC(
            ioc_type=candidate.ioc_type,
            value=candidate.value,
            extraction_source=candidate.extraction_source,
            validation_status=candidate.validation_status,
            confidence=candidate.confidence,
            first_seen=seen_at,
            last_seen=seen_at,
        )
        db.add(ioc)
        db.flush()
        return ioc, True

    if as_aware_utc(seen_at) < as_aware_utc(existing.first_seen):
        existing.first_seen = seen_at
    if as_aware_utc(seen_at) > as_aware_utc(existing.last_seen):
        existing.last_seen = seen_at
    if candidate.confidence > existing.confidence:
        existing.confidence = candidate.confidence
    return existing, False


def link_event(ioc: IOC, event: SecurityEvent) -> bool:
    """Link ioc <-> event via event_ioc if not already linked. Returns True
    if a new link was created.
    """
    if event in ioc.events:
        return False
    ioc.events.append(event)
    return True

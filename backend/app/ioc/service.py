from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ioc.base import ExtractedIOC
from app.models.event import SecurityEvent
from app.models.ioc import IOC


def _aware(value: datetime) -> datetime:
    """SQLite doesn't preserve tzinfo through a flush/refresh round-trip
    (unlike Postgres's TIMESTAMPTZ) — a naive value read back is always UTC
    by this project's convention, so treat it as such rather than let a
    naive/aware comparison raise.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


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

    if _aware(seen_at) < _aware(existing.first_seen):
        existing.first_seen = seen_at
    if _aware(seen_at) > _aware(existing.last_seen):
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

"""Two-pass IOC extraction pipeline. See DEF.md § Phase 4.

Pass 1: extract candidates from every SecurityEvent, upsert into IOC
(deduplicated by ioc_type+value), link event_ioc.

Pass 2: roll each alert's matched events' IOCs up onto alert_ioc. Runs over
every alert on every call (not scoped by `since`), so it self-heals
regardless of whether extraction or detection ran first.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ioc.field_extraction import extract_from_event
from app.ioc.service import link_event, upsert_ioc
from app.models.alert import Alert
from app.models.event import SecurityEvent
from app.schemas.ioc_run import IOCExtractionReport


def _load_events(db: Session, since: datetime | None) -> list[SecurityEvent]:
    stmt = select(SecurityEvent)
    if since is not None:
        stmt = stmt.where(SecurityEvent.occurred_at >= since)
    stmt = stmt.order_by(SecurityEvent.occurred_at)
    return list(db.scalars(stmt).all())


def run_ioc_extraction(db: Session, since: datetime | None = None) -> IOCExtractionReport:
    events = _load_events(db, since)

    iocs_created = 0
    iocs_updated = 0
    event_links_created = 0
    iocs_by_type: dict[str, int] = {}

    for event in events:
        for candidate in extract_from_event(event):
            ioc, created = upsert_ioc(db, candidate, event.occurred_at)
            if created:
                iocs_created += 1
            else:
                iocs_updated += 1
            iocs_by_type[candidate.ioc_type.value] = (
                iocs_by_type.get(candidate.ioc_type.value, 0) + 1
            )
            if link_event(ioc, event):
                event_links_created += 1

    db.flush()

    alert_links_created = 0
    for alert in db.scalars(select(Alert)).all():
        existing_ioc_ids = {ioc.id for ioc in alert.iocs}
        for matched_event in alert.events:
            for ioc in matched_event.iocs:
                if ioc.id not in existing_ioc_ids:
                    alert.iocs.append(ioc)
                    existing_ioc_ids.add(ioc.id)
                    alert_links_created += 1

    db.flush()

    return IOCExtractionReport(
        since=since,
        events_scanned=len(events),
        iocs_created=iocs_created,
        iocs_updated=iocs_updated,
        event_links_created=event_links_created,
        alert_links_created=alert_links_created,
        iocs_by_type=iocs_by_type,
    )

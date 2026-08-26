"""ORM -> API schema conversions needed by more than one router — kept
here instead of duplicated, since IOCRead's alert_ids/event_ids can't be
derived by Pydantic's automatic from_attributes conversion (IOC.alerts is
a list of Alert objects, not ids). See DEF.md § Phase 9/10.
"""

from app.models.ioc import IOC
from app.schemas.ioc import IOCRead


def to_ioc_read(ioc: IOC) -> IOCRead:
    return IOCRead(
        id=ioc.id,
        ioc_type=ioc.ioc_type,
        value=ioc.value,
        extraction_source=ioc.extraction_source,
        validation_status=ioc.validation_status,
        confidence=ioc.confidence,
        first_seen=ioc.first_seen,
        last_seen=ioc.last_seen,
        created_at=ioc.created_at,
        updated_at=ioc.updated_at,
        alert_ids=[alert.id for alert in ioc.alerts],
        event_ids=[event.id for event in ioc.events],
    )

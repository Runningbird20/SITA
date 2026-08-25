from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import as_aware_utc
from app.models.alert import Alert
from app.models.associations import AlertEntity, EventEntity
from app.models.entity import Entity
from app.models.enums import EntityRole, EntityType
from app.models.event import SecurityEvent


def upsert_host_entity(db: Session, identifier: str, seen_at: datetime) -> tuple[Entity, bool]:
    """Insert or update a host Entity by (entity_type, identifier). Returns
    (entity, created).
    """
    existing = db.scalars(
        select(Entity).where(Entity.entity_type == EntityType.HOST, Entity.identifier == identifier)
    ).one_or_none()

    if existing is None:
        entity = Entity(
            entity_type=EntityType.HOST,
            identifier=identifier,
            first_seen=seen_at,
            last_seen=seen_at,
        )
        db.add(entity)
        db.flush()
        return entity, True

    if as_aware_utc(seen_at) < as_aware_utc(existing.first_seen):
        existing.first_seen = seen_at
    if as_aware_utc(seen_at) > as_aware_utc(existing.last_seen):
        existing.last_seen = seen_at
    return existing, False


def link_event(db: Session, entity: Entity, event: SecurityEvent, role: EntityRole) -> bool:
    """Link entity <-> event via EventEntity, tagged with `role`, if not
    already linked with that same role. Returns True if a new link was
    created.
    """
    already_linked = any(
        link.entity_id == entity.id and link.role == role for link in event.entity_links
    )
    if already_linked:
        return False
    db.add(EventEntity(event=event, entity=entity, role=role))
    return True


def link_alert(db: Session, entity: Entity, alert: Alert, role: EntityRole) -> bool:
    """Roll a host entity up onto an Alert via AlertEntity, tagged with
    `role`, mirroring how Phase 4 rolls IOCs onto alert_ioc.
    """
    already_linked = any(
        link.entity_id == entity.id and link.role == role for link in alert.entity_links
    )
    if already_linked:
        return False
    db.add(AlertEntity(alert=alert, entity=entity, role=role))
    return True

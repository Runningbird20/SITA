"""Two idempotent, self-healing sync passes that make the deterministic
MITRE ATT&CK mapping real: Detection <-> MITRETechnique (rule metadata),
then Alert <-> MITRETechnique source='rule' (per-firing). See DEF.md § Phase 8.

Both passes only ever link techniques that already exist in the local
mitre_techniques table — if the loader hasn't run yet, or a rule
references a technique_id not yet vendored, that link is silently skipped
and picked up on a later run once the data exists.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.detection.registry import RULES
from app.detection.seed import ensure_detections_seeded
from app.models.alert import Alert
from app.models.associations import AlertMitreMapping
from app.models.enums import MitreMappingSource
from app.models.mitre import MITRETechnique
from app.schemas.mitre_run import MitreMappingReport


def _sync_detection_techniques(db: Session) -> int:
    detections_by_key = ensure_detections_seeded(db)
    techniques_by_id = {t.technique_id: t for t in db.scalars(select(MITRETechnique)).all()}

    links_created = 0
    for rule in RULES:
        detection = detections_by_key[rule.rule_key]
        linked_ids = {t.id for t in detection.mitre_techniques}
        for technique_id in rule.mitre_technique_ids:
            technique = techniques_by_id.get(technique_id)
            if technique is None or technique.id in linked_ids:
                continue
            detection.mitre_techniques.append(technique)
            linked_ids.add(technique.id)
            links_created += 1

    db.flush()
    return links_created


def _sync_alert_techniques(db: Session, since: datetime | None) -> tuple[int, int]:
    stmt = select(Alert)
    if since is not None:
        stmt = stmt.where(Alert.first_event_at >= since)
    alerts = list(db.scalars(stmt).all())

    mappings_created = 0
    for alert in alerts:
        existing_ids = {
            m.technique_id for m in alert.mitre_mappings if m.source == MitreMappingSource.RULE
        }
        for technique in alert.detection.mitre_techniques:
            if technique.id in existing_ids:
                continue
            db.add(
                AlertMitreMapping(
                    alert_id=alert.id,
                    technique_id=technique.id,
                    source=MitreMappingSource.RULE,
                    analysis_result_id=None,
                )
            )
            existing_ids.add(technique.id)
            mappings_created += 1

    db.flush()
    return len(alerts), mappings_created


def run_mitre_mapping(db: Session, since: datetime | None = None) -> MitreMappingReport:
    links_created = _sync_detection_techniques(db)
    alerts_processed, mappings_created = _sync_alert_techniques(db, since)

    return MitreMappingReport(
        since=since,
        detection_technique_links_created=links_created,
        alerts_processed=alerts_processed,
        alert_technique_mappings_created=mappings_created,
    )

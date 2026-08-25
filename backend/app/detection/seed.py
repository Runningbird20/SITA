from sqlalchemy import select
from sqlalchemy.orm import Session

from app.detection.registry import RULES
from app.models.detection import Detection


def ensure_detections_seeded(db: Session) -> dict[str, Detection]:
    """Idempotently upsert one Detection row per registered rule, keyed by
    rule_key — safe to call on every pipeline run. Returns a
    rule_key -> Detection mapping.
    """
    existing = {d.rule_key: d for d in db.scalars(select(Detection)).all()}
    result: dict[str, Detection] = {}
    for rule in RULES:
        detection = existing.get(rule.rule_key)
        if detection is None:
            detection = Detection(
                rule_key=rule.rule_key,
                name=rule.name,
                description=rule.description,
                category=rule.category,
                default_severity=rule.default_severity,
                enabled=True,
                config=rule.default_config or None,
            )
            db.add(detection)
            db.flush()
        result[rule.rule_key] = detection
    return result

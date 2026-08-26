"""Runs every enabled detection rule against currently-persisted
SecurityEvents and persists any resulting Alerts. See DEF.md § Phase 3.

Known limitation: this does not deduplicate. Re-running over an
already-processed time range creates duplicate Alert rows for the same
underlying events — `since` lets a caller scope a run to new data, but
avoiding overlap is the caller's responsibility. Tracked as
[[detection-run-idempotency]] in TODO.md.
"""

import logging
import time
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.metrics import alerts_created_total, detection_rule_duration_seconds
from app.detection.registry import RULES
from app.detection.seed import ensure_detections_seeded
from app.models.alert import Alert
from app.models.enums import SourceType
from app.models.event import SecurityEvent
from app.schemas.detection_run import DetectionRunReport

logger = logging.getLogger(__name__)


def _load_events(
    db: Session, source_types: tuple[SourceType, ...], since: datetime | None
) -> list[SecurityEvent]:
    stmt = select(SecurityEvent).where(SecurityEvent.source_type.in_(source_types))
    if since is not None:
        stmt = stmt.where(SecurityEvent.occurred_at >= since)
    stmt = stmt.order_by(SecurityEvent.occurred_at)
    return list(db.scalars(stmt).all())


def run_detection(db: Session, since: datetime | None = None) -> DetectionRunReport:
    detections_by_key = ensure_detections_seeded(db)
    alerts_by_rule: dict[str, int] = {rule.rule_key: 0 for rule in RULES}
    alerts_created = 0

    for rule in RULES:
        detection = detections_by_key[rule.rule_key]
        if not detection.enabled:
            continue

        events = _load_events(db, rule.source_types, since)
        event_lookup = {e.id: e for e in events}
        config = detection.config or rule.default_config

        start = time.monotonic()
        findings = list(rule.evaluate(db, events, config))
        detection_rule_duration_seconds.labels(rule_key=rule.rule_key).observe(
            time.monotonic() - start
        )

        for finding in findings:
            alert = Alert(
                detection_id=detection.id,
                severity=finding.severity,
                confidence=finding.confidence,
                rationale=finding.rationale,
                severity_factors=finding.severity_factors,
                first_event_at=finding.first_event_at,
                last_event_at=finding.last_event_at,
            )
            for event_id in finding.matched_event_ids:
                matched_event = event_lookup.get(event_id)
                if matched_event is not None:
                    alert.events.append(matched_event)
            db.add(alert)
            alerts_created += 1
            alerts_by_rule[rule.rule_key] += 1

        if findings:
            alerts_created_total.labels(rule_key=rule.rule_key).inc(len(findings))

    db.flush()

    logger.info(
        "detection run completed",
        extra={
            "since": since.isoformat() if since else None,
            "rules_run": len(RULES),
            "alerts_created": alerts_created,
            "alerts_by_rule": alerts_by_rule,
        },
    )

    return DetectionRunReport(
        since=since,
        rules_run=len(RULES),
        alerts_created=alerts_created,
        alerts_by_rule=alerts_by_rule,
    )

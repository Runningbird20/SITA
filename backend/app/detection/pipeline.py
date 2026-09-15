"""Runs every enabled detection rule against currently-persisted
SecurityEvents and persists any resulting Alerts. See DEF.md § Phase 3.

Idempotent re-runs: a finding whose fingerprint (detection_id + sorted
matched event IDs) already exists as an Alert is skipped rather than
duplicated — resolves [[detection-run-idempotency]], see DEF.md § Phase 3
"Post-roadmap addition". `since` still scopes which events a rule
considers (for performance), but overlap no longer risks duplicate Alerts.

Cross-rule dedup: a finding whose matched-event set exactly matches an
*existing* Alert's — regardless of which rule produced either one — is
also skipped, and the rule that would have duplicated it is recorded onto
the alert that already exists instead. Resolves [[cross-rule-dedup]], see
DEF.md § Phase 3 "Post-roadmap addition: cross-rule fingerprint dedup".
"""

import logging
import time
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.metrics import (
    alerts_created_total,
    alerts_cross_rule_duplicate_skipped_total,
    alerts_duplicate_skipped_total,
    detection_rule_duration_seconds,
)
from app.detection.base import compute_alert_fingerprint, compute_evidence_fingerprint
from app.detection.registry import RULES
from app.detection.seed import ensure_detections_seeded
from app.models.alert import Alert
from app.models.associations import alert_event
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


def _load_evidence_index(db: Session) -> dict[str, Alert]:
    """Every existing Alert, keyed by the evidence fingerprint of its own
    matched-event set — built from the `alert_event` junction directly
    (event IDs only), not by loading full SecurityEvent rows, since only
    the IDs are needed to compute the hash.
    """
    event_ids_by_alert: dict = defaultdict(list)
    for alert_id, event_id in db.execute(
        select(alert_event.c.alert_id, alert_event.c.event_id)
    ).all():
        event_ids_by_alert[alert_id].append(event_id)
    if not event_ids_by_alert:
        return {}

    alerts_by_id = {a.id: a for a in db.scalars(select(Alert)).all()}
    return {
        compute_evidence_fingerprint(event_ids): alerts_by_id[alert_id]
        for alert_id, event_ids in event_ids_by_alert.items()
        if alert_id in alerts_by_id
    }


def run_detection(db: Session, since: datetime | None = None) -> DetectionRunReport:
    detections_by_key = ensure_detections_seeded(db)
    alerts_by_rule: dict[str, int] = {rule.rule_key: 0 for rule in RULES}
    alerts_created = 0
    duplicates_skipped = 0
    cross_rule_duplicates_skipped = 0
    # One query for the whole run, not per rule/finding — updated in-memory
    # as new alerts are added so two identical findings within this same
    # run also can't double-create.
    seen_fingerprints = set(db.scalars(select(Alert.fingerprint)).all())
    # Same idea, keyed on evidence alone (not detection_id) — lets a
    # different rule's finding over the identical matched-event set be
    # recognized as "already covered," whether the covering alert was
    # created earlier this run or in a past one.
    evidence_index = _load_evidence_index(db)

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

        rule_duplicates = 0
        rule_cross_rule_duplicates = 0
        for finding in findings:
            fingerprint = compute_alert_fingerprint(detection.id, finding.matched_event_ids)
            if fingerprint in seen_fingerprints:
                rule_duplicates += 1
                continue

            evidence_fingerprint = compute_evidence_fingerprint(finding.matched_event_ids)
            covering_alert = evidence_index.get(evidence_fingerprint)
            if covering_alert is not None:
                also_detected_by = set(covering_alert.severity_factors.get("also_detected_by", []))
                also_detected_by.add(rule.rule_key)
                covering_alert.severity_factors = {
                    **covering_alert.severity_factors,
                    "also_detected_by": sorted(also_detected_by),
                }
                rule_cross_rule_duplicates += 1
                continue

            seen_fingerprints.add(fingerprint)

            alert = Alert(
                detection_id=detection.id,
                fingerprint=fingerprint,
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
            evidence_index[evidence_fingerprint] = alert
            alerts_created += 1
            alerts_by_rule[rule.rule_key] += 1

        if alerts_by_rule[rule.rule_key]:
            alerts_created_total.labels(rule_key=rule.rule_key).inc(alerts_by_rule[rule.rule_key])
        if rule_duplicates:
            alerts_duplicate_skipped_total.labels(rule_key=rule.rule_key).inc(rule_duplicates)
            duplicates_skipped += rule_duplicates
        if rule_cross_rule_duplicates:
            alerts_cross_rule_duplicate_skipped_total.labels(rule_key=rule.rule_key).inc(
                rule_cross_rule_duplicates
            )
            cross_rule_duplicates_skipped += rule_cross_rule_duplicates

    db.flush()

    logger.info(
        "detection run completed",
        extra={
            "since": since.isoformat() if since else None,
            "rules_run": len(RULES),
            "alerts_created": alerts_created,
            "alerts_by_rule": alerts_by_rule,
            "duplicates_skipped": duplicates_skipped,
            "cross_rule_duplicates_skipped": cross_rule_duplicates_skipped,
        },
    )

    return DetectionRunReport(
        since=since,
        rules_run=len(RULES),
        alerts_created=alerts_created,
        alerts_by_rule=alerts_by_rule,
        duplicates_skipped=duplicates_skipped,
        cross_rule_duplicates_skipped=cross_rule_duplicates_skipped,
    )

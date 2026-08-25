"""Groups Alerts into Incidents. See DEF.md § Phase 5.

Two passes:
1. Host-entity population: for every SecurityEvent, extract host
   candidates (bridging hostname/IP identity via host_identity.py where
   known), upsert Entity(type=host), link event_entity.
2. Chronological grouping: for every Alert without an incident_id, in
   first_event_at order, score it against open/investigating candidate
   incidents within the time window and join the best match, or start a
   new incident. Not scoped to `since` for candidate-incident lookup —
   only which alerts get processed is scoped, matching Phase 3/4's
   "since limits new work, not historical context" convention.
"""

from dataclasses import asdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.correlation.base import (
    AlertSignature,
    CorrelationConfig,
    IncidentSignature,
    ScoreBreakdown,
)
from app.correlation.entity_service import link_alert, link_event, upsert_host_entity
from app.correlation.host_extraction import extract_host_candidates
from app.correlation.scoring import score_alert_against_incident
from app.correlation.title import generate_title
from app.models.alert import Alert
from app.models.enums import EntityType, IncidentStatus, Severity
from app.models.event import SecurityEvent
from app.models.incident import Incident
from app.schemas.correlation_run import CorrelationRunReport

_SEVERITY_ORDER = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]


def _max_severity(a: Severity, b: Severity) -> Severity:
    return a if _SEVERITY_ORDER.index(a) >= _SEVERITY_ORDER.index(b) else b


def _load_events(db: Session, since: datetime | None) -> list[SecurityEvent]:
    stmt = select(SecurityEvent)
    if since is not None:
        stmt = stmt.where(SecurityEvent.occurred_at >= since)
    stmt = stmt.order_by(SecurityEvent.occurred_at)
    return list(db.scalars(stmt).all())


def _build_alert_signature(alert: Alert) -> AlertSignature:
    ioc_ids = {ioc.id for ioc in alert.iocs}
    host_entity_ids = set()
    for event in alert.events:
        for link in event.entity_links:
            if link.entity.entity_type == EntityType.HOST:
                host_entity_ids.add(link.entity_id)
    technique_ids = {mapping.technique_id for mapping in alert.mitre_mappings}
    return AlertSignature(
        alert_id=alert.id,
        ioc_ids=ioc_ids,
        host_entity_ids=host_entity_ids,
        technique_ids=technique_ids,
        first_event_at=alert.first_event_at,
        last_event_at=alert.last_event_at,
    )


def _build_incident_signature_from_db(db: Session, incident: Incident) -> IncidentSignature:
    sig = IncidentSignature(incident_id=incident.id)
    alerts = db.scalars(select(Alert).where(Alert.incident_id == incident.id)).all()
    for alert in alerts:
        sig.merge(_build_alert_signature(alert))
    return sig


def _load_candidate_incidents(
    db: Session, alert_sig: AlertSignature, config: CorrelationConfig
) -> list[Incident]:
    cutoff = alert_sig.first_event_at - timedelta(seconds=config.window_seconds)
    stmt = select(Incident).where(
        Incident.status.in_([IncidentStatus.OPEN, IncidentStatus.INVESTIGATING]),
        Incident.last_activity_at >= cutoff,
    )
    return list(db.scalars(stmt).all())


def _breakdown_to_dict(breakdown: ScoreBreakdown | None) -> dict | None:
    if breakdown is None:
        return None
    return {
        "time_score": breakdown.time_score,
        "ioc_score": breakdown.ioc_score,
        "host_score": breakdown.host_score,
        "mitre_score": breakdown.mitre_score,
        "shared_ioc_ids": [str(i) for i in breakdown.shared_ioc_ids],
        "shared_host_ids": [str(i) for i in breakdown.shared_host_ids],
        "shared_technique_ids": [str(i) for i in breakdown.shared_technique_ids],
    }


def run_correlation(db: Session, since: datetime | None = None) -> CorrelationRunReport:
    config = CorrelationConfig()

    # Pass 1: host entity population, over every event (not scoped to
    # `since` — historical context matters for identity, same reasoning as
    # Phase 4's IOC extraction).
    host_entities_created = 0
    host_links_created = 0
    for event in _load_events(db, None):
        for identifier, role in extract_host_candidates(event):
            entity, created = upsert_host_entity(db, identifier, event.occurred_at)
            if created:
                host_entities_created += 1
            if link_event(db, entity, event, role):
                host_links_created += 1
    db.flush()

    # Pass 2: chronological grouping of not-yet-correlated alerts.
    alert_stmt = select(Alert).where(Alert.incident_id.is_(None))
    if since is not None:
        alert_stmt = alert_stmt.where(Alert.first_event_at >= since)
    alert_stmt = alert_stmt.order_by(Alert.first_event_at)
    alerts = list(db.scalars(alert_stmt).all())

    incident_signatures: dict = {}
    incidents_created = 0
    incidents_joined = 0

    for alert in alerts:
        alert_sig = _build_alert_signature(alert)

        best_incident: Incident | None = None
        best_score = 0.0
        best_breakdown: ScoreBreakdown | None = None

        for candidate in _load_candidate_incidents(db, alert_sig, config):
            if candidate.id not in incident_signatures:
                incident_signatures[candidate.id] = _build_incident_signature_from_db(db, candidate)
            candidate_sig = incident_signatures[candidate.id]
            breakdown = score_alert_against_incident(alert_sig, candidate_sig, config)
            if breakdown.total > best_score:
                best_score = breakdown.total
                best_incident = candidate
                best_breakdown = breakdown

        joined = best_incident is not None and best_score >= config.correlation_threshold
        if joined:
            incident = best_incident
        else:
            incident = Incident(
                title="",
                status=IncidentStatus.OPEN,
                severity=Severity.LOW,
                first_activity_at=alert.first_event_at,
                last_activity_at=alert.last_event_at,
                correlation_method={},
            )
            db.add(incident)
            db.flush()
            incident_signatures[incident.id] = IncidentSignature(incident_id=incident.id)
            incidents_created += 1

        alert.incident = incident
        incident_signatures[incident.id].merge(alert_sig)
        sig = incident_signatures[incident.id]

        for event in alert.events:
            for link in event.entity_links:
                if link.entity.entity_type == EntityType.HOST:
                    link_alert(db, link.entity, alert, link.role)

        incident.first_activity_at = sig.first_activity_at
        incident.last_activity_at = sig.last_activity_at
        incident.severity = _max_severity(incident.severity, alert.severity)
        incident.title = generate_title(list(incident.alerts))

        method = dict(incident.correlation_method or {})
        alerts_method = dict(method.get("alerts", {}))
        alerts_method[str(alert.id)] = {
            "joined": joined,
            "score": best_score if joined else None,
            "signals": _breakdown_to_dict(best_breakdown if joined else None),
        }
        method["alerts"] = alerts_method
        method["config"] = asdict(config)
        incident.correlation_method = method

        if joined:
            incidents_joined += 1

    db.flush()

    return CorrelationRunReport(
        since=since,
        alerts_processed=len(alerts),
        incidents_created=incidents_created,
        incidents_joined=incidents_joined,
        host_entities_created=host_entities_created,
        host_links_created=host_links_created,
    )

"""Gathers an Incident and its alerts into the one deterministic text block
every Phase 7 prompt embeds. See DEF.md § Phase 7.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.models.enums import MitreMappingSource
from app.models.incident import Incident


@dataclass
class AlertContext:
    alert_id: uuid.UUID
    detection_name: str
    category: str
    severity: str
    confidence: float
    rationale: str
    first_event_at: datetime
    last_event_at: datetime


@dataclass
class IncidentContext:
    incident_id: uuid.UUID
    title: str
    status: str
    severity: str
    first_activity_at: datetime
    last_activity_at: datetime
    alerts: list[AlertContext] = field(default_factory=list)
    ioc_summaries: list[str] = field(default_factory=list)
    rule_mitre_techniques: list[str] = field(default_factory=list)


def build_incident_context(incident: Incident) -> IncidentContext:
    alerts = [
        AlertContext(
            alert_id=alert.id,
            detection_name=alert.detection.name,
            category=str(alert.detection.category),
            severity=str(alert.severity),
            confidence=alert.confidence,
            rationale=alert.rationale,
            first_event_at=alert.first_event_at,
            last_event_at=alert.last_event_at,
        )
        for alert in incident.alerts
    ]

    ioc_summaries: list[str] = []
    seen_iocs: set[uuid.UUID] = set()
    for alert in incident.alerts:
        for ioc in alert.iocs:
            if ioc.id not in seen_iocs:
                seen_iocs.add(ioc.id)
                ioc_summaries.append(f"{ioc.ioc_type!s}: {ioc.value}")

    rule_mitre_techniques: list[str] = []
    seen_techniques: set[str] = set()
    for alert in incident.alerts:
        for mapping in alert.mitre_mappings:
            if mapping.source != MitreMappingSource.RULE:
                continue
            technique_id = mapping.technique.technique_id
            if technique_id not in seen_techniques:
                seen_techniques.add(technique_id)
                rule_mitre_techniques.append(technique_id)

    return IncidentContext(
        incident_id=incident.id,
        title=incident.title,
        status=str(incident.status),
        severity=str(incident.severity),
        first_activity_at=incident.first_activity_at,
        last_activity_at=incident.last_activity_at,
        alerts=alerts,
        ioc_summaries=ioc_summaries,
        rule_mitre_techniques=rule_mitre_techniques,
    )


def render_context_block(ctx: IncidentContext) -> str:
    lines = [
        f"Incident: {ctx.title}",
        f"Status: {ctx.status}    Deterministic severity: {ctx.severity}",
        f"Activity window: {ctx.first_activity_at.isoformat()} to {ctx.last_activity_at.isoformat()}",
        "",
        f"Alerts ({len(ctx.alerts)}):",
    ]
    for alert in ctx.alerts:
        lines.append(
            f"- [{alert.severity}] {alert.detection_name} ({alert.category}), "
            f"confidence={alert.confidence:.2f}: {alert.rationale} "
            f"(window {alert.first_event_at.isoformat()} to {alert.last_event_at.isoformat()})"
        )

    lines.append("")
    lines.append("Known IOCs:")
    if ctx.ioc_summaries:
        lines.extend(f"- {summary}" for summary in ctx.ioc_summaries)
    else:
        lines.append("- none extracted")

    lines.append("")
    lines.append("Existing deterministic MITRE ATT&CK mappings:")
    if ctx.rule_mitre_techniques:
        lines.extend(f"- {technique_id}" for technique_id in ctx.rule_mitre_techniques)
    else:
        lines.append("- none yet")

    return "\n".join(lines)

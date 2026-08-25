"""Deterministic incident title generation. See DEF.md § Phase 5."""

from typing import TYPE_CHECKING

from app.models.enums import IOCType

if TYPE_CHECKING:
    from app.models.alert import Alert


def _primary_identifier(alert: "Alert") -> str | None:
    for link in alert.entity_links:
        return link.entity.identifier
    for ioc in alert.iocs:
        if ioc.ioc_type in (IOCType.IPV4, IOCType.IPV6):
            return ioc.value
    return None


def generate_title(alerts: list["Alert"]) -> str:
    ordered = sorted(alerts, key=lambda a: a.first_event_at)

    if len(ordered) == 1:
        alert = ordered[0]
        identifier = _primary_identifier(alert)
        return f"{alert.detection.name} — {identifier}" if identifier else alert.detection.name

    seen_names: list[str] = []
    for alert in ordered:
        name = alert.detection.name
        if name not in seen_names:
            seen_names.append(name)
    return " → ".join(seen_names)

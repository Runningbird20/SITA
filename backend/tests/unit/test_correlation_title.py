from datetime import UTC, datetime, timedelta

from app.correlation.title import generate_title
from app.models.alert import Alert
from app.models.detection import Detection
from app.models.enums import AlertStatus, ExtractionSource, IOCType, ValidationStatus
from app.models.ioc import IOC

NOW = datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC)


def _detection(name: str) -> Detection:
    return Detection(
        rule_key=name.lower().replace(" ", "_"),
        name=name,
        description="...",
        category="authentication",
        default_severity="medium",
    )


def _alert(detection: Detection, offset_seconds: int) -> Alert:
    when = NOW + timedelta(seconds=offset_seconds)
    return Alert(
        detection=detection,
        severity="medium",
        confidence=0.7,
        status=AlertStatus.NEW,
        rationale="test",
        severity_factors={},
        first_event_at=when,
        last_event_at=when,
    )


class TestGenerateTitle:
    def test_single_alert_with_no_identifier_uses_rule_name_only(self):
        alert = _alert(_detection("SSH Brute Force"), 0)
        assert generate_title([alert]) == "SSH Brute Force"

    def test_multiple_alerts_ordered_chronologically(self):
        d1, d2, d3 = (
            _detection("SSH Brute Force"),
            _detection("Port Scanning"),
            _detection("Suspicious PowerShell Activity"),
        )
        a1 = _alert(d1, 0)
        a2 = _alert(d2, 300)
        a3 = _alert(d3, 600)
        # pass out of order to prove sorting happens internally
        title = generate_title([a3, a1, a2])
        assert title == "SSH Brute Force → Port Scanning → Suspicious PowerShell Activity"

    def test_repeated_rule_name_deduplicated(self):
        detection = _detection("SSH Brute Force")
        a1 = _alert(detection, 0)
        a2 = _alert(detection, 300)
        title = generate_title([a1, a2])
        assert title == "SSH Brute Force"

    def test_single_alert_falls_back_to_ip_ioc_when_no_entity_link(self):
        # No AlertEntity link (the primary identifier source), but there is
        # an IPv4 IOC — generate_title should fall back to it.
        alert = _alert(_detection("Port Scanning"), 0)
        alert.iocs.append(
            IOC(
                ioc_type=IOCType.IPV4,
                value="198.51.100.9",
                extraction_source=ExtractionSource.REGEX,
                validation_status=ValidationStatus.VALID,
                confidence=0.7,
                first_seen=NOW,
                last_seen=NOW,
            )
        )
        assert generate_title([alert]) == "Port Scanning — 198.51.100.9"

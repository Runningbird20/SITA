import re
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.detection.base import DetectionRule, RuleFinding, score_severity
from app.models.enums import DetectionCategory, Severity, SourceType
from app.models.event import SecurityEvent

_INDICATOR_PATTERNS: dict[str, re.Pattern[str]] = {
    "add_admin_account": re.compile(
        r"net\s+(user|localgroup\s+administrators).*\s+/add", re.IGNORECASE
    ),
    "privilege_enumeration": re.compile(r"whoami\s+/priv|whoami\s+/all|sudo\s+-l\b", re.IGNORECASE),
    "setuid_bit": re.compile(r"chmod\s+(\+s|[24-7]?[0-7]?7[0-7]{2})\b", re.IGNORECASE),
    "elevated_shell": re.compile(r"runas\s+/user:|sudo\s+su\b|\bpkexec\b", re.IGNORECASE),
    "uac_bypass": re.compile(r"fodhelper\.exe|eventvwr\.exe.*mmc|sdclt\.exe", re.IGNORECASE),
}


class PrivilegeEscalationRule(DetectionRule):
    rule_key = "privilege_escalation"
    name = "Privilege Escalation Pattern"
    description = (
        "A process command line matching known privilege-escalation "
        "indicators: creating/adding a local administrator account, "
        "enumerating current privileges or sudo rights, setting the "
        "setuid bit, an elevated-shell invocation, or a known UAC-bypass "
        "binary sequence. Confidence scales with how many distinct "
        "indicator categories match."
    )
    category = DetectionCategory.ENDPOINT
    default_severity = Severity.HIGH
    source_types = (SourceType.ENDPOINT,)
    default_config: dict = {}
    mitre_technique_ids = ("T1548.001", "T1548.002", "T1548.003", "T1136.001")

    def evaluate(
        self, db: Session, events: Sequence[SecurityEvent], config: dict
    ) -> list[RuleFinding]:
        findings: list[RuleFinding] = []
        for event in events:
            command_line = event.normalized.get("command_line") or ""
            if not command_line:
                continue

            matched_categories = [
                category
                for category, pattern in _INDICATOR_PATTERNS.items()
                if pattern.search(command_line)
            ]
            if not matched_categories:
                continue

            confidence = min(0.95, 0.55 + 0.15 * (len(matched_categories) - 1))
            severity, factors = score_severity(self.default_severity, len(matched_categories), 1)
            rationale = (
                f"Command line matched privilege-escalation indicators: "
                f"{', '.join(matched_categories)}. Command: {command_line[:200]!r}"
            )
            findings.append(
                RuleFinding(
                    matched_event_ids=[event.id],
                    severity=severity,
                    confidence=confidence,
                    rationale=rationale,
                    severity_factors={**factors, "matched_categories": matched_categories},
                    first_event_at=event.occurred_at,
                    last_event_at=event.occurred_at,
                )
            )
        return findings

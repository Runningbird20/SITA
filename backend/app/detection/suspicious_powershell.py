import re
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.detection.base import DetectionRule, RuleFinding, score_severity
from app.models.enums import DetectionCategory, Severity, SourceType
from app.models.event import SecurityEvent

_INDICATOR_PATTERNS: dict[str, re.Pattern[str]] = {
    "encoded_command": re.compile(r"-enc(odedcommand)?\b", re.IGNORECASE),
    "hidden_window": re.compile(r"-w(indowstyle)?\s+hidden", re.IGNORECASE),
    "exec_policy_bypass": re.compile(r"-exec(utionpolicy)?\s+bypass", re.IGNORECASE),
    "download_cradle": re.compile(
        r"downloadstring|downloadfile|invoke-expression|\biex\b|net\.webclient|invoke-webrequest",
        re.IGNORECASE,
    ),
}


class SuspiciousPowerShellRule(DetectionRule):
    rule_key = "suspicious_powershell"
    name = "Suspicious PowerShell Activity"
    description = (
        "A powershell.exe command line matching known-suspicious indicators: "
        "base64-encoded commands, hidden windows, execution-policy bypass, "
        "or a download-and-execute cradle. Confidence scales with how many "
        "distinct indicator categories match."
    )
    category = DetectionCategory.ENDPOINT
    default_severity = Severity.HIGH
    source_types = (SourceType.ENDPOINT,)
    default_config: dict = {}

    def evaluate(
        self, db: Session, events: Sequence[SecurityEvent], config: dict
    ) -> list[RuleFinding]:
        findings: list[RuleFinding] = []
        for event in events:
            process_name = (event.normalized.get("process_name") or "").lower()
            command_line = event.normalized.get("command_line") or ""
            if "powershell" not in process_name:
                continue

            matched_categories = [
                category
                for category, pattern in _INDICATOR_PATTERNS.items()
                if pattern.search(command_line)
            ]
            if not matched_categories:
                continue

            confidence = min(0.95, 0.5 + 0.15 * (len(matched_categories) - 1))
            severity, factors = score_severity(self.default_severity, len(matched_categories), 1)
            rationale = (
                f"powershell command line matched indicators: {', '.join(matched_categories)}. "
                f"Command: {command_line[:200]!r}"
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

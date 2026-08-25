from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.detection.base import DetectionRule, RuleFinding, score_severity
from app.models.enums import DetectionCategory, Severity, SourceType
from app.models.event import SecurityEvent


class SuspiciousAuthPatternRule(DetectionRule):
    rule_key = "suspicious_auth_pattern"
    name = "Suspicious Authentication Pattern"
    description = (
        "Two independent heuristics on successful logins: an off-hours login "
        "(UTC), or a login from a source IP never seen before for that "
        "username despite the user having an established login history."
    )
    category = DetectionCategory.AUTHENTICATION
    default_severity = Severity.MEDIUM
    source_types = (SourceType.AUTH,)
    default_config = {"off_hours_start": 0, "off_hours_end": 5}

    def evaluate(
        self, db: Session, events: Sequence[SecurityEvent], config: dict
    ) -> list[RuleFinding]:
        off_hours_start = config.get("off_hours_start", self.default_config["off_hours_start"])
        off_hours_end = config.get("off_hours_end", self.default_config["off_hours_end"])

        successes = [e for e in events if e.normalized.get("event_result") == "success"]
        if not successes:
            return []

        # Full auth-success history — deliberately not limited to the
        # candidate window, per DEF.md § Phase 3.
        all_auth_events = db.scalars(
            select(SecurityEvent).where(SecurityEvent.source_type == SourceType.AUTH)
        ).all()
        all_successes = [
            e for e in all_auth_events if e.normalized.get("event_result") == "success"
        ]

        findings: list[RuleFinding] = []
        for event in successes:
            username = event.normalized.get("username")
            source_ip = event.normalized.get("source_ip")
            if not username or not source_ip:
                continue

            if off_hours_start <= event.occurred_at.hour <= off_hours_end:
                severity, factors = score_severity(self.default_severity, 1, 1)
                findings.append(
                    RuleFinding(
                        matched_event_ids=[event.id],
                        severity=severity,
                        confidence=0.55,
                        rationale=(
                            f"{username!r} logged in at {event.occurred_at.isoformat()} UTC, "
                            "outside normal hours."
                        ),
                        severity_factors=factors,
                        first_event_at=event.occurred_at,
                        last_event_at=event.occurred_at,
                    )
                )

            prior_ips = {
                e.normalized.get("source_ip")
                for e in all_successes
                if e.normalized.get("username") == username
                and e.occurred_at < event.occurred_at
                and e.id != event.id
            }
            prior_ips.discard(None)
            if prior_ips and source_ip not in prior_ips:
                severity, factors = score_severity(self.default_severity, 1, 1)
                findings.append(
                    RuleFinding(
                        matched_event_ids=[event.id],
                        severity=severity,
                        confidence=0.6,
                        rationale=(
                            f"{username!r} logged in from {source_ip!r}, a source IP not seen "
                            f"in this user's prior login history ({sorted(prior_ips)})."
                        ),
                        severity_factors=factors,
                        first_event_at=event.occurred_at,
                        last_event_at=event.occurred_at,
                    )
                )
        return findings

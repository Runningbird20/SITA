from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.detection.base import DetectionRule, RuleFinding, score_severity
from app.models.enums import DetectionCategory, Severity, SourceType
from app.models.event import SecurityEvent


class PasswordSprayingRule(DetectionRule):
    rule_key = "password_spraying"
    name = "Password Spraying"
    description = (
        "One source IP attempting authentication against many distinct "
        "usernames, each only a handful of times — the inverse shape of "
        "brute force, designed to stay under per-account lockout thresholds."
    )
    category = DetectionCategory.AUTHENTICATION
    default_severity = Severity.HIGH
    source_types = (SourceType.AUTH,)
    default_config = {
        "distinct_username_threshold": 5,
        "max_attempts_per_username": 3,
        "window_seconds": 600,
    }

    def evaluate(
        self, db: Session, events: Sequence[SecurityEvent], config: dict
    ) -> list[RuleFinding]:
        distinct_threshold = config.get(
            "distinct_username_threshold", self.default_config["distinct_username_threshold"]
        )
        max_attempts = config.get(
            "max_attempts_per_username", self.default_config["max_attempts_per_username"]
        )
        window_seconds = config.get("window_seconds", self.default_config["window_seconds"])

        by_source: dict[str, list[SecurityEvent]] = defaultdict(list)
        for event in events:
            if event.normalized.get("event_result") != "failure":
                continue
            source_ip = event.normalized.get("source_ip")
            if not source_ip:
                continue
            by_source[source_ip].append(event)

        findings: list[RuleFinding] = []
        for source_ip, attempts in by_source.items():
            attempts.sort(key=lambda e: e.occurred_at)

            best_matched: list[SecurityEvent] = []
            best_distinct = 0
            left = 0
            for right in range(len(attempts)):
                while (
                    attempts[right].occurred_at - attempts[left].occurred_at
                ).total_seconds() > window_seconds:
                    left += 1
                window = attempts[left : right + 1]
                usernames = {e.normalized.get("username") for e in window}
                if len(usernames) > best_distinct:
                    best_distinct = len(usernames)
                    best_matched = window

            if best_distinct < distinct_threshold:
                continue
            attempts_per_username = len(best_matched) / best_distinct
            if attempts_per_username > max_attempts:
                continue

            first_event_at = best_matched[0].occurred_at
            last_event_at = best_matched[-1].occurred_at
            severity, factors = score_severity(
                self.default_severity, best_distinct, distinct_threshold
            )
            rationale = (
                f"{source_ip!r} attempted authentication against {best_distinct} distinct "
                f"usernames ({attempts_per_username:.1f} attempts/username on average) within "
                f"{(last_event_at - first_event_at).total_seconds():.0f}s."
            )
            findings.append(
                RuleFinding(
                    matched_event_ids=[e.id for e in best_matched],
                    severity=severity,
                    confidence=0.8,
                    rationale=rationale,
                    severity_factors=factors,
                    first_event_at=first_event_at,
                    last_event_at=last_event_at,
                )
            )
        return findings

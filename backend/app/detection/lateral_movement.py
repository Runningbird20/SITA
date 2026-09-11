from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.detection.base import DetectionRule, RuleFinding, score_severity
from app.models.enums import DetectionCategory, Severity, SourceType
from app.models.event import SecurityEvent


class LateralMovementRule(DetectionRule):
    rule_key = "lateral_movement"
    name = "Lateral Movement"
    description = (
        "One account successfully authenticating to many distinct internal "
        "hosts within a short window — normal users rarely hop between "
        "several machines in minutes; a compromised credential or stolen "
        "session token being reused across a network typically does."
    )
    category = DetectionCategory.AUTHENTICATION
    default_severity = Severity.HIGH
    source_types = (SourceType.AUTH,)
    default_config = {"min_distinct_hosts": 3, "window_seconds": 600}
    mitre_technique_ids = ("T1021",)
    primary_threshold_key = "min_distinct_hosts"

    def evaluate(
        self, db: Session, events: Sequence[SecurityEvent], config: dict
    ) -> list[RuleFinding]:
        min_distinct_hosts = config.get(
            "min_distinct_hosts", self.default_config["min_distinct_hosts"]
        )
        window_seconds = config.get("window_seconds", self.default_config["window_seconds"])

        by_username: dict[str, list[SecurityEvent]] = defaultdict(list)
        for event in events:
            if event.normalized.get("event_result") != "success":
                continue
            username = event.normalized.get("username")
            dest_host = event.normalized.get("dest_host")
            if not username or not dest_host:
                continue
            by_username[username].append(event)

        findings: list[RuleFinding] = []
        for username, successes in by_username.items():
            successes.sort(key=lambda e: e.occurred_at)

            # Not app.detection.windowing.densest_window — that maximizes
            # raw event count, which would favor 5 logins to one host over
            # 3 logins to 3 distinct hosts, exactly backwards from what
            # this rule needs to catch.
            best_window: list[SecurityEvent] = []
            best_distinct = 0
            left = 0
            for right in range(len(successes)):
                while (
                    successes[right].occurred_at - successes[left].occurred_at
                ).total_seconds() > window_seconds:
                    left += 1
                candidate = successes[left : right + 1]
                distinct = {e.normalized.get("dest_host") for e in candidate}
                if len(distinct) > best_distinct:
                    best_distinct = len(distinct)
                    best_window = candidate

            if best_distinct < min_distinct_hosts:
                continue

            window = best_window
            distinct_hosts = {e.normalized.get("dest_host") for e in window}

            first_event_at = window[0].occurred_at
            last_event_at = window[-1].occurred_at
            severity, factors = score_severity(
                self.default_severity, len(distinct_hosts), min_distinct_hosts
            )
            rationale = (
                f"{username!r} authenticated successfully to {len(distinct_hosts)} distinct "
                f"hosts ({', '.join(sorted(distinct_hosts))}) within "
                f"{(last_event_at - first_event_at).total_seconds():.0f}s."
            )

            findings.append(
                RuleFinding(
                    matched_event_ids=[e.id for e in window],
                    severity=severity,
                    confidence=0.6,
                    rationale=rationale,
                    severity_factors={**factors, "distinct_hosts": len(distinct_hosts)},
                    first_event_at=first_event_at,
                    last_event_at=last_event_at,
                )
            )
        return findings

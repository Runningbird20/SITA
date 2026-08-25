from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.detection.base import DetectionRule, RuleFinding, score_severity
from app.detection.windowing import densest_window
from app.models.enums import DetectionCategory, Severity, SourceType
from app.models.event import SecurityEvent


class RepeatedAuthFailuresRule(DetectionRule):
    rule_key = "repeated_auth_failures"
    name = "Repeated Authentication Failures"
    description = (
        "A high volume of authentication failures against one target host "
        "from at least several distinct source IPs within a window — "
        "distributed, noisy failure activity that a single-source rule like "
        "SSH brute force would miss, since no individual source crosses its "
        "own threshold."
    )
    category = DetectionCategory.AUTHENTICATION
    default_severity = Severity.MEDIUM
    source_types = (SourceType.AUTH,)
    default_config = {
        "failure_threshold": 20,
        "distinct_source_ip_minimum": 3,
        "window_seconds": 900,
    }
    mitre_technique_ids = ("T1110",)

    def evaluate(
        self, db: Session, events: Sequence[SecurityEvent], config: dict
    ) -> list[RuleFinding]:
        threshold = config.get("failure_threshold", self.default_config["failure_threshold"])
        min_sources = config.get(
            "distinct_source_ip_minimum", self.default_config["distinct_source_ip_minimum"]
        )
        window_seconds = config.get("window_seconds", self.default_config["window_seconds"])

        by_host: dict[str, list[SecurityEvent]] = defaultdict(list)
        for event in events:
            if event.normalized.get("event_result") != "failure":
                continue
            dest_host = event.normalized.get("dest_host")
            if dest_host:
                by_host[dest_host].append(event)

        findings: list[RuleFinding] = []
        for dest_host, failures in by_host.items():
            failures.sort(key=lambda e: e.occurred_at)
            timestamps = [e.occurred_at for e in failures]
            count, start, end = densest_window(timestamps, window_seconds)
            if count < threshold:
                continue

            matched = failures[start : end + 1]
            distinct_ips = {e.normalized.get("source_ip") for e in matched}
            distinct_ips.discard(None)
            if len(distinct_ips) < min_sources:
                continue

            first_event_at = matched[0].occurred_at
            last_event_at = matched[-1].occurred_at
            severity, factors = score_severity(self.default_severity, count, threshold)
            rationale = (
                f"{count} failed authentication attempts against {dest_host!r} from "
                f"{len(distinct_ips)} distinct source IPs within "
                f"{(last_event_at - first_event_at).total_seconds():.0f}s."
            )
            findings.append(
                RuleFinding(
                    matched_event_ids=[e.id for e in matched],
                    severity=severity,
                    confidence=0.7,
                    rationale=rationale,
                    severity_factors={**factors, "distinct_source_ips": len(distinct_ips)},
                    first_event_at=first_event_at,
                    last_event_at=last_event_at,
                )
            )
        return findings

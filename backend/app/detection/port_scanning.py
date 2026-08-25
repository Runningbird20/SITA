from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.detection.base import DetectionRule, RuleFinding, score_severity
from app.models.enums import DetectionCategory, Severity, SourceType
from app.models.event import SecurityEvent


class PortScanningRule(DetectionRule):
    rule_key = "port_scanning"
    name = "Port Scanning"
    description = (
        "One source IP touching many distinct destination ports in a short "
        "window — reconnaissance behavior, not normal client traffic."
    )
    category = DetectionCategory.NETWORK
    default_severity = Severity.MEDIUM
    source_types = (SourceType.NETWORK,)
    default_config = {"distinct_port_threshold": 6, "window_seconds": 60}

    def evaluate(
        self, db: Session, events: Sequence[SecurityEvent], config: dict
    ) -> list[RuleFinding]:
        distinct_threshold = config.get(
            "distinct_port_threshold", self.default_config["distinct_port_threshold"]
        )
        window_seconds = config.get("window_seconds", self.default_config["window_seconds"])

        by_source: dict[str, list[SecurityEvent]] = defaultdict(list)
        for event in events:
            src_ip = event.normalized.get("src_ip")
            if src_ip:
                by_source[src_ip].append(event)

        findings: list[RuleFinding] = []
        for src_ip, conns in by_source.items():
            conns.sort(key=lambda e: e.occurred_at)

            best_matched: list[SecurityEvent] = []
            best_distinct = 0
            left = 0
            for right in range(len(conns)):
                while (
                    conns[right].occurred_at - conns[left].occurred_at
                ).total_seconds() > window_seconds:
                    left += 1
                window = conns[left : right + 1]
                ports = {e.normalized.get("dst_port") for e in window}
                if len(ports) > best_distinct:
                    best_distinct = len(ports)
                    best_matched = window

            if best_distinct < distinct_threshold:
                continue

            first_event_at = best_matched[0].occurred_at
            last_event_at = best_matched[-1].occurred_at
            dst_ips = {e.normalized.get("dst_ip") for e in best_matched}
            severity, factors = score_severity(
                self.default_severity, best_distinct, distinct_threshold
            )
            rationale = (
                f"{src_ip!r} connected to {best_distinct} distinct destination ports on "
                f"{sorted(dst_ips)} within {(last_event_at - first_event_at).total_seconds():.0f}s."
            )
            findings.append(
                RuleFinding(
                    matched_event_ids=[e.id for e in best_matched],
                    severity=severity,
                    confidence=0.75,
                    rationale=rationale,
                    severity_factors=factors,
                    first_event_at=first_event_at,
                    last_event_at=last_event_at,
                )
            )
        return findings

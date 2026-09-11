import ipaddress
from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.detection.base import DetectionRule, RuleFinding, score_severity
from app.models.enums import DetectionCategory, Severity, SourceType
from app.models.event import SecurityEvent

# RFC 1918 private ranges only — deliberately *not* Python's own
# `ip.is_private`, which also marks the RFC 5737 documentation/TEST-NET
# ranges (198.51.100.0/24, 203.0.113.0/24, 192.0.2.0/24) as private. This
# project's own synthetic data uses those specific ranges throughout to
# represent external/attacker addresses (the same convention already
# established for `.example` domains in app/ioc/base.py's RESERVED_TLDS) —
# treating them as "private" here would make this rule unable to fire
# against its own target fixture. Caught by running the rule against a
# real fixture and getting zero alerts, the same way the DNS tunneling
# rule's base-domain bug was caught earlier.
_RFC1918_NETS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)


def _is_external(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    if ip.is_loopback or ip.is_link_local:
        return False
    return not any(ip in net for net in _RFC1918_NETS)


class DataExfiltrationRule(DetectionRule):
    rule_key = "data_exfiltration"
    name = "Data Exfiltration Volume"
    description = (
        "One internal host sending an unusually large volume of outbound "
        "bytes to external destinations within a short window — a large, "
        "concentrated outbound transfer is one of the few signals that "
        "survives even when the destination and protocol both look "
        "otherwise unremarkable."
    )
    category = DetectionCategory.NETWORK
    default_severity = Severity.HIGH
    source_types = (SourceType.NETWORK,)
    default_config = {"bytes_threshold": 52_428_800, "window_seconds": 300}  # 50 MiB
    mitre_technique_ids = ("T1041",)
    primary_threshold_key = "bytes_threshold"

    def evaluate(
        self, db: Session, events: Sequence[SecurityEvent], config: dict
    ) -> list[RuleFinding]:
        bytes_threshold = config.get("bytes_threshold", self.default_config["bytes_threshold"])
        window_seconds = config.get("window_seconds", self.default_config["window_seconds"])

        by_src: dict[str, list[SecurityEvent]] = defaultdict(list)
        for event in events:
            src_ip = event.normalized.get("src_ip")
            dst_ip = event.normalized.get("dst_ip")
            bytes_sent = event.normalized.get("bytes_sent")
            if not src_ip or not dst_ip or bytes_sent is None:
                continue
            if not _is_external(dst_ip):
                continue
            by_src[src_ip].append(event)

        findings: list[RuleFinding] = []
        for src_ip, outbound in by_src.items():
            outbound.sort(key=lambda e: e.occurred_at)

            best_window: list[SecurityEvent] = []
            best_total = 0
            left = 0
            for right in range(len(outbound)):
                while (
                    outbound[right].occurred_at - outbound[left].occurred_at
                ).total_seconds() > window_seconds:
                    left += 1
                candidate = outbound[left : right + 1]
                total = sum(e.normalized["bytes_sent"] for e in candidate)
                if total > best_total:
                    best_total = total
                    best_window = candidate

            if best_total < bytes_threshold:
                continue

            window = best_window
            first_event_at = window[0].occurred_at
            last_event_at = window[-1].occurred_at
            destinations = sorted({e.normalized.get("dst_ip") for e in window})
            severity, factors = score_severity(self.default_severity, best_total, bytes_threshold)
            rationale = (
                f"{src_ip!r} sent {best_total / 1_048_576:.1f} MiB to {len(destinations)} "
                f"external destination(s) ({', '.join(destinations[:3])}"
                f"{'...' if len(destinations) > 3 else ''}) within "
                f"{(last_event_at - first_event_at).total_seconds():.0f}s."
            )

            findings.append(
                RuleFinding(
                    matched_event_ids=[e.id for e in window],
                    severity=severity,
                    confidence=0.6,
                    rationale=rationale,
                    severity_factors={**factors, "total_bytes_sent": best_total},
                    first_event_at=first_event_at,
                    last_event_at=last_event_at,
                )
            )
        return findings

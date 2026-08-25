from collections import defaultdict
from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy.orm import Session

from app.detection.base import DetectionRule, RuleFinding, score_severity
from app.detection.windowing import densest_window
from app.models.enums import DetectionCategory, Severity, SourceType
from app.models.event import SecurityEvent


class SSHBruteForceRule(DetectionRule):
    rule_key = "ssh_brute_force"
    name = "SSH Brute Force"
    description = (
        "Repeated authentication failures from one source IP against one "
        "target host within a short window — a classic credential-guessing "
        "pattern. Escalates to critical if a login from the same source and "
        "target succeeds shortly after."
    )
    category = DetectionCategory.AUTHENTICATION
    default_severity = Severity.HIGH
    source_types = (SourceType.AUTH,)
    default_config = {"failure_threshold": 10, "window_seconds": 300}

    def evaluate(
        self, db: Session, events: Sequence[SecurityEvent], config: dict
    ) -> list[RuleFinding]:
        threshold = config.get("failure_threshold", self.default_config["failure_threshold"])
        window_seconds = config.get("window_seconds", self.default_config["window_seconds"])

        groups: dict[tuple[str, str], list[SecurityEvent]] = defaultdict(list)
        successes: dict[tuple[str, str], list[SecurityEvent]] = defaultdict(list)
        for event in events:
            source_ip = event.normalized.get("source_ip")
            dest_host = event.normalized.get("dest_host")
            if not source_ip or not dest_host:
                continue
            key = (source_ip, dest_host)
            if event.normalized.get("event_result") == "failure":
                groups[key].append(event)
            elif event.normalized.get("event_result") == "success":
                successes[key].append(event)

        findings: list[RuleFinding] = []
        for key, failures in groups.items():
            failures.sort(key=lambda e: e.occurred_at)
            timestamps = [e.occurred_at for e in failures]
            count, start, end = densest_window(timestamps, window_seconds)
            if count < threshold:
                continue

            matched = failures[start : end + 1]
            first_event_at = matched[0].occurred_at
            last_event_at = matched[-1].occurred_at
            source_ip, dest_host = key

            followed_by_success = None
            cutoff = last_event_at + timedelta(seconds=window_seconds)
            for success in sorted(successes.get(key, []), key=lambda e: e.occurred_at):
                if last_event_at <= success.occurred_at <= cutoff:
                    followed_by_success = success
                    break

            severity, factors = score_severity(self.default_severity, count, threshold)
            confidence = 0.85
            rationale = (
                f"{count} failed authentication attempts against {dest_host!r} "
                f"from {source_ip!r} within "
                f"{(last_event_at - first_event_at).total_seconds():.0f}s."
            )
            matched_ids = [e.id for e in matched]

            if followed_by_success is not None:
                severity = Severity.CRITICAL
                factors = {**factors, "followed_by_success": True}
                confidence = min(1.0, confidence + 0.1)
                rationale += (
                    f" Followed by a successful login from the same source at "
                    f"{followed_by_success.occurred_at.isoformat()} — likely compromised."
                )
                matched_ids.append(followed_by_success.id)
                last_event_at = followed_by_success.occurred_at

            findings.append(
                RuleFinding(
                    matched_event_ids=matched_ids,
                    severity=severity,
                    confidence=confidence,
                    rationale=rationale,
                    severity_factors=factors,
                    first_event_at=first_event_at,
                    last_event_at=last_event_at,
                )
            )
        return findings

import statistics
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.detection.base import DetectionRule, RuleFinding, score_severity
from app.models.enums import DetectionCategory, Severity, SourceType
from app.models.event import SecurityEvent

_STDEV_FLOOR = 0.5


def _day_start(day: date) -> datetime:
    # UTC-aware, matching SecurityEvent.occurred_at (DateTime(timezone=True))
    # and this project's UTC-everywhere convention (see
    # suspicious_auth_pattern's off-hours check, which assumes the same).
    return datetime.combine(day, time.min, tzinfo=UTC)


class AnomalousEventVolumeRule(DetectionRule):
    """Deterministic, still — an adaptive threshold (per-host, per-source-type
    z-score against that host's own history) rather than a fixed one, catching
    volume spikes a fixed-threshold rule can't. `mitre_technique_ids` maps to
    T1496 (Resource Hijacking) as the most broadly-fitting example of "why
    would one host's activity volume suddenly spike," not a precise claim —
    see DEF.md § Phase 3 "Post-roadmap addition" for the honest caveat on fit.
    """

    rule_key = "anomalous_event_volume"
    name = "Anomalous Event Volume"
    description = (
        "A host's daily event count for one source type is many standard "
        "deviations above that same host's own prior-day baseline — a "
        "volume spike unusual for this specific host, regardless of "
        "whether any single event in it looks suspicious on its own."
    )
    category = DetectionCategory.ANOMALY
    default_severity = Severity.MEDIUM
    source_types = (
        SourceType.AUTH,
        SourceType.ENDPOINT,
        SourceType.NETWORK,
        SourceType.DNS,
        SourceType.WEB,
    )
    default_config = {
        "min_baseline_days": 3,
        "z_score_threshold": 3.0,
        "min_current_day_count": 5,
    }
    mitre_technique_ids = ("T1496",)

    def evaluate(
        self, db: Session, events: Sequence[SecurityEvent], config: dict
    ) -> list[RuleFinding]:
        min_baseline_days = config.get(
            "min_baseline_days", self.default_config["min_baseline_days"]
        )
        z_threshold = config.get("z_score_threshold", self.default_config["z_score_threshold"])
        min_current_day_count = config.get(
            "min_current_day_count", self.default_config["min_current_day_count"]
        )

        # Candidate (source_type, host, day) groups come only from the
        # passed-in events window, never from a broader db query — matched
        # events must be a subset of what the pipeline itself loaded (see
        # run_detection's event_lookup), so only these events can ever be
        # cited as evidence. The db query below is for baseline history
        # only, which never contributes matched_event_ids.
        candidate_groups: dict[tuple[SourceType, str, date], list[SecurityEvent]] = defaultdict(
            list
        )
        for event in events:
            if not event.source_host:
                continue
            candidate_groups[
                (event.source_type, event.source_host, event.occurred_at.date())
            ].append(event)

        findings: list[RuleFinding] = []
        for (source_type, host, day), day_events in candidate_groups.items():
            current_count = len(day_events)
            day_start = _day_start(day)

            prior_events = db.scalars(
                select(SecurityEvent).where(
                    SecurityEvent.source_type == source_type,
                    SecurityEvent.source_host == host,
                    SecurityEvent.occurred_at < day_start,
                )
            ).all()
            daily_counts: dict[date, int] = defaultdict(int)
            for prior_event in prior_events:
                daily_counts[prior_event.occurred_at.date()] += 1
            baseline_counts = list(daily_counts.values())

            if len(baseline_counts) < min_baseline_days:
                continue
            if current_count < min_current_day_count:
                continue

            mean = statistics.mean(baseline_counts)
            stdev = max(statistics.pstdev(baseline_counts), _STDEV_FLOOR)
            z_score = (current_count - mean) / stdev
            if z_score < z_threshold:
                continue

            statistical_threshold = max(1, round(mean + z_threshold * stdev))
            severity, factors = score_severity(
                self.default_severity, current_count, statistical_threshold
            )
            first_event_at = min(e.occurred_at for e in day_events)
            last_event_at = max(e.occurred_at for e in day_events)

            rationale = (
                f"{host!r} had {current_count} {source_type} event(s) on "
                f"{day.isoformat()}, {z_score:.1f} standard deviations above its "
                f"{len(baseline_counts)}-day baseline (mean {mean:.1f}, stdev "
                f"{stdev:.1f})."
            )

            findings.append(
                RuleFinding(
                    matched_event_ids=[e.id for e in day_events],
                    severity=severity,
                    confidence=0.55,
                    rationale=rationale,
                    severity_factors={
                        **factors,
                        "z_score": round(z_score, 2),
                        "baseline_mean": round(mean, 2),
                        "baseline_stdev": round(stdev, 2),
                        "baseline_days": len(baseline_counts),
                    },
                    first_event_at=first_event_at,
                    last_event_at=last_event_at,
                )
            )
        return findings

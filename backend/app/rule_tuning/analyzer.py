"""Resolves WHATNEXT.md's "Analyst feedback closing the loop into rule
tuning" item: marking an alert as a false positive previously fed back
into nothing. See DEF.md § Phase 3, "Post-roadmap addition: rule tuning
suggestions from analyst feedback".

Fully deterministic — a plain rate computation and a fixed-percentage
threshold adjustment, no LLM involved anywhere in this loop, matching
this project's founding principle that the AI is never the source of
truth for a detection/severity decision. Suggestions are advisory only:
nothing here writes to Detection.config automatically. An admin applies
one explicitly via PATCH /detections/{id}/config (a separate, deliberate
action) if they agree with it.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.detection.registry import RULES
from app.models.alert import Alert
from app.models.detection import Detection
from app.models.enums import AlertStatus


@dataclass(frozen=True)
class TuningSuggestion:
    rule_key: str
    rule_name: str
    total_alerts: int
    false_positive_count: int
    false_positive_rate: float
    threshold_key: str
    current_threshold_value: float
    suggested_threshold_value: float
    rationale: str

    def as_dict(self) -> dict:
        return {
            "rule_key": self.rule_key,
            "rule_name": self.rule_name,
            "total_alerts": self.total_alerts,
            "false_positive_count": self.false_positive_count,
            "false_positive_rate": round(self.false_positive_rate, 3),
            "threshold_key": self.threshold_key,
            "current_threshold_value": self.current_threshold_value,
            "suggested_threshold_value": self.suggested_threshold_value,
            "rationale": self.rationale,
        }


def _suggest_new_value(current_value, increase_fraction: float):
    suggested = current_value * (1 + increase_fraction)
    if isinstance(current_value, int):
        # Always at least +1 — a fractional increase on a small integer
        # threshold (e.g. failure_threshold=3) could otherwise round back
        # down to the same value and suggest a no-op change.
        return max(current_value + 1, round(suggested))
    return round(suggested, 4)


def compute_tuning_suggestions(
    db: Session,
    min_sample_size: int = 10,
    false_positive_rate_threshold: float = 0.5,
    increase_fraction: float = 0.2,
) -> list[TuningSuggestion]:
    """One suggestion per rule whose alerts (a) number at least
    `min_sample_size` (enough data to mean something — a rule with 2
    alerts and 1 false positive is a 50% rate on essentially no
    evidence) and (b) have a false-positive rate at or above
    `false_positive_rate_threshold`. Rules with no
    `primary_threshold_key` (keyword-matching rules like
    suspicious_powershell, or rules with no single sensitivity knob) are
    skipped — there's nothing to suggest raising.
    """
    suggestions: list[TuningSuggestion] = []

    for rule in RULES:
        if rule.primary_threshold_key is None:
            continue

        detection = db.scalars(select(Detection).where(Detection.rule_key == rule.rule_key)).first()
        if detection is None:
            continue

        alerts = list(db.scalars(select(Alert).where(Alert.detection_id == detection.id)).all())
        total = len(alerts)
        if total < min_sample_size:
            continue

        false_positive_count = sum(1 for a in alerts if a.status == AlertStatus.FALSE_POSITIVE)
        false_positive_rate = false_positive_count / total
        if false_positive_rate < false_positive_rate_threshold:
            continue

        config = detection.config or rule.default_config
        current_value = config.get(
            rule.primary_threshold_key, rule.default_config.get(rule.primary_threshold_key)
        )
        if current_value is None:
            continue
        suggested_value = _suggest_new_value(current_value, increase_fraction)

        suggestions.append(
            TuningSuggestion(
                rule_key=rule.rule_key,
                rule_name=rule.name,
                total_alerts=total,
                false_positive_count=false_positive_count,
                false_positive_rate=false_positive_rate,
                threshold_key=rule.primary_threshold_key,
                current_threshold_value=current_value,
                suggested_threshold_value=suggested_value,
                rationale=(
                    f"{false_positive_count} of {total} alerts "
                    f"({false_positive_rate:.0%}) were marked false positive. "
                    f"Raising {rule.primary_threshold_key!r} from {current_value} to "
                    f"{suggested_value} would require more evidence before this rule "
                    f"fires, reducing sensitivity."
                ),
            )
        )

    return suggestions

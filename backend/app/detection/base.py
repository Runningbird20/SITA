"""The detection rule contract. Every rule validates *this* — a candidate
window of events in, zero or more findings out — never anything LLM-derived.
See DEF.md § Phase 3 for the full design.
"""

import hashlib
import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from app.models.event import SecurityEvent

from sqlalchemy.orm import Session

from app.models.enums import DetectionCategory, Severity, SourceType


@dataclass
class RuleFinding:
    matched_event_ids: list[uuid.UUID]
    severity: Severity
    confidence: float
    rationale: str
    severity_factors: dict
    first_event_at: datetime
    last_event_at: datetime


def compute_alert_fingerprint(detection_id: uuid.UUID, matched_event_ids: list[uuid.UUID]) -> str:
    """Identifies "the same finding" regardless of what `since` window
    produced it — resolves `[[detection-run-idempotency]]`, see DEF.md §
    Phase 3 "Post-roadmap addition". Sorted before hashing so the result
    doesn't depend on the order a rule happens to return matches in.
    """
    sorted_ids = sorted(str(event_id) for event_id in matched_event_ids)
    raw = f"{detection_id}:{','.join(sorted_ids)}"
    return hashlib.sha256(raw.encode()).hexdigest()


def compute_evidence_fingerprint(matched_event_ids: list[uuid.UUID]) -> str:
    """Identifies "the same exact set of evidence," deliberately without a
    detection_id — resolves `[[cross-rule-dedup]]`, see DEF.md § Phase 3
    "Post-roadmap addition: cross-rule fingerprint dedup". Two different
    rules that land on the identical matched-event set both hash to this
    same value, unlike `compute_alert_fingerprint` above, which is scoped
    per-rule by design.
    """
    sorted_ids = sorted(str(event_id) for event_id in matched_event_ids)
    return hashlib.sha256(",".join(sorted_ids).encode()).hexdigest()


_SEVERITY_WEIGHT: dict[Severity, float] = {
    Severity.LOW: 0.25,
    Severity.MEDIUM: 0.5,
    Severity.HIGH: 0.75,
    Severity.CRITICAL: 1.0,
}


def score_severity(base: Severity, matched_count: int, threshold: int) -> tuple[Severity, dict]:
    """Deterministic severity scoring: a rule's `default_severity` is a
    baseline, adjusted by how far over its own threshold this particular
    finding is. See DEF.md § Phase 3 for the formula and rationale.
    """
    rule_weight = _SEVERITY_WEIGHT[base]
    volume_ratio = matched_count / threshold if threshold else 1.0
    volume_factor = min(0.3, 0.05 * volume_ratio)
    asset_sensitivity = 0.0
    score = min(1.0, rule_weight + volume_factor + asset_sensitivity)

    if score >= 0.90:
        severity = Severity.CRITICAL
    elif score >= 0.70:
        severity = Severity.HIGH
    elif score >= 0.45:
        severity = Severity.MEDIUM
    else:
        severity = Severity.LOW

    return severity, {
        "rule_weight": rule_weight,
        "volume_factor": volume_factor,
        "asset_sensitivity": asset_sensitivity,
        "score": score,
    }


class DetectionRule(ABC):
    """Instances are stateless — `evaluate()` is a pure function of its
    arguments, so the same rule instance is reused across every pipeline run.
    """

    rule_key: ClassVar[str]
    name: ClassVar[str]
    description: ClassVar[str]
    category: ClassVar[DetectionCategory]
    default_severity: ClassVar[Severity]
    source_types: ClassVar[tuple[SourceType, ...]]
    default_config: ClassVar[dict] = {}
    mitre_technique_ids: ClassVar[tuple[str, ...]] = ()

    @abstractmethod
    def evaluate(
        self, db: Session, events: Sequence["SecurityEvent"], config: dict
    ) -> list[RuleFinding]:
        """`events` is every persisted SecurityEvent whose source_type is in
        `source_types` (and, if the pipeline was given a `since` cutoff,
        whose occurred_at >= since), ordered by occurred_at. `config` is
        this rule's Detection.config, falling back to default_config if
        unset. `db` is available for rules needing history beyond the
        candidate window (e.g. suspicious_auth_pattern, impossible_travel).
        """

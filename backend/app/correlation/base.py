"""Core types for correlation: the scoring config, per-alert and
per-incident signatures, and the score breakdown. See DEF.md § Phase 5.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.core.time import as_aware_utc


@dataclass
class CorrelationConfig:
    window_seconds: int = 3600
    time_weight: float = 0.2
    time_decay_seconds: int = 1800
    ioc_weight: float = 0.4
    ioc_saturation: int = 1
    host_weight: float = 0.3
    host_saturation: int = 1
    mitre_weight: float = 0.1
    mitre_saturation: int = 1
    correlation_threshold: float = 0.4


@dataclass
class AlertSignature:
    alert_id: uuid.UUID
    ioc_ids: set[uuid.UUID]
    host_entity_ids: set[uuid.UUID]
    technique_ids: set[uuid.UUID]
    first_event_at: datetime
    last_event_at: datetime

    def __post_init__(self) -> None:
        self.first_event_at = as_aware_utc(self.first_event_at)
        self.last_event_at = as_aware_utc(self.last_event_at)


@dataclass
class IncidentSignature:
    incident_id: uuid.UUID
    ioc_ids: set[uuid.UUID] = field(default_factory=set)
    host_entity_ids: set[uuid.UUID] = field(default_factory=set)
    technique_ids: set[uuid.UUID] = field(default_factory=set)
    first_activity_at: datetime | None = None
    last_activity_at: datetime | None = None

    def merge(self, alert_sig: AlertSignature) -> None:
        self.ioc_ids |= alert_sig.ioc_ids
        self.host_entity_ids |= alert_sig.host_entity_ids
        self.technique_ids |= alert_sig.technique_ids
        self.first_activity_at = (
            alert_sig.first_event_at
            if self.first_activity_at is None
            else min(self.first_activity_at, alert_sig.first_event_at)
        )
        self.last_activity_at = (
            alert_sig.last_event_at
            if self.last_activity_at is None
            else max(self.last_activity_at, alert_sig.last_event_at)
        )


@dataclass
class ScoreBreakdown:
    time_score: float
    ioc_score: float
    host_score: float
    mitre_score: float
    shared_ioc_ids: set[uuid.UUID]
    shared_host_ids: set[uuid.UUID]
    shared_technique_ids: set[uuid.UUID]

    @property
    def total(self) -> float:
        return self.time_score + self.ioc_score + self.host_score + self.mitre_score

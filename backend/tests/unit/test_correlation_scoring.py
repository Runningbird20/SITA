import uuid
from datetime import UTC, datetime, timedelta

from app.correlation.base import AlertSignature, CorrelationConfig, IncidentSignature
from app.correlation.scoring import score_alert_against_incident

NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
CONFIG = CorrelationConfig()


def _alert_sig(**overrides) -> AlertSignature:
    defaults = {
        "alert_id": uuid.uuid4(),
        "ioc_ids": set(),
        "host_entity_ids": set(),
        "technique_ids": set(),
        "first_event_at": NOW,
        "last_event_at": NOW,
    }
    defaults.update(overrides)
    return AlertSignature(**defaults)


def _incident_sig(**overrides) -> IncidentSignature:
    defaults = {
        "incident_id": uuid.uuid4(),
        "ioc_ids": set(),
        "host_entity_ids": set(),
        "technique_ids": set(),
        "first_activity_at": NOW,
        "last_activity_at": NOW,
    }
    defaults.update(overrides)
    return IncidentSignature(**defaults)


class TestTimeScore:
    def test_overlapping_ranges_score_full_time_weight(self):
        alert = _alert_sig(first_event_at=NOW, last_event_at=NOW + timedelta(minutes=5))
        incident = _incident_sig(first_activity_at=NOW, last_activity_at=NOW + timedelta(minutes=5))
        breakdown = score_alert_against_incident(alert, incident, CONFIG)
        assert breakdown.time_score == CONFIG.time_weight

    def test_score_decays_with_gap(self):
        alert = _alert_sig(
            first_event_at=NOW + timedelta(minutes=15), last_event_at=NOW + timedelta(minutes=15)
        )
        incident = _incident_sig(first_activity_at=NOW, last_activity_at=NOW)
        breakdown = score_alert_against_incident(alert, incident, CONFIG)
        assert 0 < breakdown.time_score < CONFIG.time_weight

    def test_gap_beyond_decay_window_scores_zero(self):
        alert = _alert_sig(
            first_event_at=NOW + timedelta(hours=2), last_event_at=NOW + timedelta(hours=2)
        )
        incident = _incident_sig(first_activity_at=NOW, last_activity_at=NOW)
        breakdown = score_alert_against_incident(alert, incident, CONFIG)
        assert breakdown.time_score == 0.0

    def test_alert_before_incident_window_still_decays_by_gap(self):
        # The alert happened *before* the incident's activity window, not
        # after — the other branch of the gap calculation.
        alert = _alert_sig(
            first_event_at=NOW - timedelta(minutes=15), last_event_at=NOW - timedelta(minutes=15)
        )
        incident = _incident_sig(first_activity_at=NOW, last_activity_at=NOW + timedelta(minutes=5))
        breakdown = score_alert_against_incident(alert, incident, CONFIG)
        assert 0 < breakdown.time_score < CONFIG.time_weight

    def test_incident_with_no_activity_window_yet_scores_full_time_weight(self):
        # A brand-new IncidentSignature before any alert has been merged
        # into it — first_activity_at/last_activity_at are still None.
        # _time_gap_seconds treats "no window yet" as a zero gap (nothing
        # to conflict with), so this scores the *full* time weight, not
        # zero — confirmed here rather than assumed.
        alert = _alert_sig(first_event_at=NOW, last_event_at=NOW)
        incident = _incident_sig(first_activity_at=None, last_activity_at=None)
        breakdown = score_alert_against_incident(alert, incident, CONFIG)
        assert breakdown.time_score == CONFIG.time_weight


class TestIOCScore:
    def test_shared_iocs_at_saturation_score_full_weight(self):
        shared = {uuid.uuid4(), uuid.uuid4()}
        alert = _alert_sig(ioc_ids=shared, first_event_at=NOW, last_event_at=NOW)
        incident = _incident_sig(ioc_ids=set(shared), first_activity_at=NOW, last_activity_at=NOW)
        breakdown = score_alert_against_incident(alert, incident, CONFIG)
        assert breakdown.ioc_score == CONFIG.ioc_weight
        assert breakdown.shared_ioc_ids == shared

    def test_one_shared_ioc_scores_full_weight(self):
        # ioc_saturation=1: a single shared high-specificity indicator (IP,
        # domain, hash, url, email — username is filtered out before this
        # function ever sees it, see
        # test_correlation_pipeline.py::TestBuildAlertSignature) is treated
        # as decisive on its own, not partial credit requiring a second
        # match. See DEF.md § Phase 5, "Shared-IOC correlation: username
        # excluded, ioc_saturation lowered to 1 (post-roadmap)".
        shared_id = uuid.uuid4()
        alert = _alert_sig(ioc_ids={shared_id}, first_event_at=NOW, last_event_at=NOW)
        incident = _incident_sig(ioc_ids={shared_id}, first_activity_at=NOW, last_activity_at=NOW)
        breakdown = score_alert_against_incident(alert, incident, CONFIG)
        assert breakdown.ioc_score == CONFIG.ioc_weight

    def test_no_shared_iocs_scores_zero(self):
        alert = _alert_sig(ioc_ids={uuid.uuid4()}, first_event_at=NOW, last_event_at=NOW)
        incident = _incident_sig(
            ioc_ids={uuid.uuid4()}, first_activity_at=NOW, last_activity_at=NOW
        )
        breakdown = score_alert_against_incident(alert, incident, CONFIG)
        assert breakdown.ioc_score == 0.0
        assert breakdown.shared_ioc_ids == set()


class TestHostScore:
    def test_one_shared_host_scores_full_weight(self):
        shared_id = uuid.uuid4()
        alert = _alert_sig(host_entity_ids={shared_id}, first_event_at=NOW, last_event_at=NOW)
        incident = _incident_sig(
            host_entity_ids={shared_id}, first_activity_at=NOW, last_activity_at=NOW
        )
        breakdown = score_alert_against_incident(alert, incident, CONFIG)
        assert breakdown.host_score == CONFIG.host_weight


class TestThresholdBehavior:
    def test_shared_ioc_alone_crosses_threshold(self):
        shared = {uuid.uuid4(), uuid.uuid4()}
        far_future = NOW + timedelta(days=1)
        alert = _alert_sig(ioc_ids=shared, first_event_at=far_future, last_event_at=far_future)
        incident = _incident_sig(ioc_ids=set(shared), first_activity_at=NOW, last_activity_at=NOW)
        breakdown = score_alert_against_incident(alert, incident, CONFIG)
        assert breakdown.total >= CONFIG.correlation_threshold

    def test_time_proximity_alone_never_crosses_threshold(self):
        alert = _alert_sig(first_event_at=NOW, last_event_at=NOW)
        incident = _incident_sig(first_activity_at=NOW, last_activity_at=NOW)
        breakdown = score_alert_against_incident(alert, incident, CONFIG)
        assert breakdown.total < CONFIG.correlation_threshold

    def test_shared_host_plus_time_proximity_crosses_threshold(self):
        shared_id = uuid.uuid4()
        alert = _alert_sig(
            host_entity_ids={shared_id},
            first_event_at=NOW + timedelta(minutes=2),
            last_event_at=NOW + timedelta(minutes=2),
        )
        incident = _incident_sig(
            host_entity_ids={shared_id}, first_activity_at=NOW, last_activity_at=NOW
        )
        breakdown = score_alert_against_incident(alert, incident, CONFIG)
        assert breakdown.total >= CONFIG.correlation_threshold

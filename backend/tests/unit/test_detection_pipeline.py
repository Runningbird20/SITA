import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.metrics import (
    alerts_created_total,
    alerts_duplicate_skipped_total,
    detection_rule_duration_seconds,
)
from app.detection.base import compute_alert_fingerprint, compute_evidence_fingerprint
from app.detection.pipeline import run_detection
from app.models.alert import Alert
from app.models.detection import Detection
from app.models.enums import SourceType

NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


class TestRunDetection:
    def test_persists_alert_linked_to_matched_events_and_detection(self, db_session, make_event):
        events = [
            make_event(
                SourceType.AUTH,
                NOW + timedelta(seconds=i * 20),
                {
                    "event_result": "failure",
                    "username": "admin",
                    "source_ip": "198.51.100.1",
                    "dest_host": "db01.internal",
                    "auth_method": "password",
                },
            )
            for i in range(10)
        ]
        db_session.commit()

        report = run_detection(db_session)
        db_session.commit()

        assert report.rules_run == 9
        assert report.alerts_by_rule["ssh_brute_force"] == 1
        assert report.alerts_created >= 1

        alert = db_session.scalars(
            select(Alert).join(Detection).where(Detection.rule_key == "ssh_brute_force")
        ).one()
        assert alert.status == "new"
        assert alert.incident_id is None
        assert {e.id for e in alert.events} == {e.id for e in events}

    def test_since_filters_out_older_events(self, db_session, make_event):
        for i in range(10):
            make_event(
                SourceType.AUTH,
                NOW + timedelta(seconds=i * 20),
                {
                    "event_result": "failure",
                    "username": "admin",
                    "source_ip": "198.51.100.1",
                    "dest_host": "db01.internal",
                    "auth_method": "password",
                },
            )
        db_session.commit()

        report = run_detection(db_session, since=NOW + timedelta(days=1))
        db_session.commit()

        assert report.alerts_by_rule["ssh_brute_force"] == 0

    def test_no_matching_events_produces_no_alerts(self, db_session):
        report = run_detection(db_session)
        db_session.commit()
        assert report.alerts_created == 0
        assert all(count == 0 for count in report.alerts_by_rule.values())


class TestComputeAlertFingerprint:
    def test_same_detection_and_events_produce_the_same_fingerprint(self):
        detection_id = uuid.uuid4()
        event_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        assert compute_alert_fingerprint(detection_id, event_ids) == compute_alert_fingerprint(
            detection_id, event_ids
        )

    def test_event_id_order_does_not_affect_the_fingerprint(self):
        detection_id = uuid.uuid4()
        event_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        forward = compute_alert_fingerprint(detection_id, event_ids)
        reversed_fp = compute_alert_fingerprint(detection_id, list(reversed(event_ids)))
        assert forward == reversed_fp

    def test_different_detection_ids_produce_different_fingerprints(self):
        event_ids = [uuid.uuid4()]
        assert compute_alert_fingerprint(uuid.uuid4(), event_ids) != compute_alert_fingerprint(
            uuid.uuid4(), event_ids
        )

    def test_different_event_sets_produce_different_fingerprints(self):
        detection_id = uuid.uuid4()
        assert compute_alert_fingerprint(detection_id, [uuid.uuid4()]) != compute_alert_fingerprint(
            detection_id, [uuid.uuid4()]
        )


class TestDetectionIdempotency:
    """Resolves [[detection-run-idempotency]] — see DEF.md § Phase 3
    'Post-roadmap addition'. Re-running detection over an overlapping
    window must not create duplicate Alerts.
    """

    def test_rerunning_over_the_same_events_creates_no_duplicate_alerts(
        self, db_session, make_event
    ):
        for i in range(10):
            make_event(
                SourceType.AUTH,
                NOW + timedelta(seconds=i * 20),
                {
                    "event_result": "failure",
                    "username": "admin",
                    "source_ip": "198.51.100.1",
                    "dest_host": "db01.internal",
                    "auth_method": "password",
                },
            )
        db_session.commit()

        first = run_detection(db_session)
        db_session.commit()
        assert first.alerts_created >= 1
        assert first.duplicates_skipped == 0

        duplicates_before = alerts_duplicate_skipped_total.labels(
            rule_key="ssh_brute_force"
        )._value.get()

        second = run_detection(db_session)
        db_session.commit()

        assert second.alerts_created == 0
        assert second.duplicates_skipped == first.alerts_created
        assert (
            alerts_duplicate_skipped_total.labels(rule_key="ssh_brute_force")._value.get()
            == duplicates_before + 1
        )

        # Not just the report's word for it — confirm directly against the DB.
        all_alerts = db_session.scalars(
            select(Alert).join(Detection).where(Detection.rule_key == "ssh_brute_force")
        ).all()
        assert len(all_alerts) == 1
        fingerprints = [a.fingerprint for a in all_alerts]
        assert len(fingerprints) == len(set(fingerprints))

    def test_a_genuinely_new_finding_is_still_created_after_a_rerun(self, db_session, make_event):
        for i in range(10):
            make_event(
                SourceType.AUTH,
                NOW + timedelta(seconds=i * 20),
                {
                    "event_result": "failure",
                    "username": "admin",
                    "source_ip": "198.51.100.1",
                    "dest_host": "db01.internal",
                    "auth_method": "password",
                },
            )
        db_session.commit()
        run_detection(db_session)
        db_session.commit()

        # A second, distinct burst against a different host — a genuinely
        # new finding, not a re-run of the first.
        for i in range(10):
            make_event(
                SourceType.AUTH,
                NOW + timedelta(hours=1, seconds=i * 20),
                {
                    "event_result": "failure",
                    "username": "admin",
                    "source_ip": "198.51.100.2",
                    "dest_host": "app02.internal",
                    "auth_method": "password",
                },
            )
        db_session.commit()

        report = run_detection(db_session)
        db_session.commit()

        assert report.alerts_by_rule["ssh_brute_force"] == 1
        assert report.duplicates_skipped >= 1  # the first burst, seen again


class TestCrossRuleDedup:
    """Resolves [[cross-rule-dedup]] — see DEF.md § Phase 3 'Post-roadmap
    addition: cross-rule fingerprint dedup'. Two different rules landing on
    the exact same matched-event set must produce one Alert, not two.
    """

    def _baseline_success(self, make_event, day_offset):
        day = NOW.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=day_offset)
        return [
            make_event(
                SourceType.AUTH,
                day + timedelta(minutes=i * 5),
                {
                    "event_result": "success",
                    "username": "jsmith",
                    "source_ip": "10.0.0.50",
                    "dest_host": "db01.internal",
                    "auth_method": "password",
                },
                host="db01.internal",
            )
            for i in range(2)
        ]

    def test_ssh_brute_force_and_anomalous_volume_collapse_into_one_alert(
        self, db_session, make_event
    ):
        # 3 quiet baseline days (2 successful logins/day) so
        # anomalous_event_volume has a real baseline to compare against.
        events = []
        for day_offset in range(3):
            events += self._baseline_success(make_event, day_offset)

        # Day 4: 10 failed attempts from one source IP against the same
        # host — and nothing else that day for this host — so
        # ssh_brute_force's matched set and anomalous_event_volume's
        # (AUTH, db01.internal, day) group are the exact same 10 events.
        attack_day = NOW.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=3)
        events += [
            make_event(
                SourceType.AUTH,
                attack_day + timedelta(seconds=i * 20),
                {
                    "event_result": "failure",
                    "username": "admin",
                    "source_ip": "198.51.100.1",
                    "dest_host": "db01.internal",
                    "auth_method": "password",
                },
                host="db01.internal",
            )
            for i in range(10)
        ]
        db_session.commit()

        report = run_detection(db_session)
        db_session.commit()

        assert report.alerts_by_rule["ssh_brute_force"] == 1
        assert report.alerts_by_rule["anomalous_event_volume"] == 0
        assert report.cross_rule_duplicates_skipped == 1

        alerts = db_session.scalars(select(Alert)).all()
        matching = [
            a
            for a in alerts
            if compute_evidence_fingerprint([e.id for e in a.events])
            == compute_evidence_fingerprint([e.id for e in events[-10:]])
        ]
        assert len(matching) == 1
        assert matching[0].severity_factors["also_detected_by"] == ["anomalous_event_volume"]

    def test_rerunning_after_a_cross_rule_dedup_stays_stable(self, db_session, make_event):
        events = []
        for day_offset in range(3):
            events += self._baseline_success(make_event, day_offset)
        attack_day = NOW.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=3)
        events += [
            make_event(
                SourceType.AUTH,
                attack_day + timedelta(seconds=i * 20),
                {
                    "event_result": "failure",
                    "username": "admin",
                    "source_ip": "198.51.100.1",
                    "dest_host": "db01.internal",
                    "auth_method": "password",
                },
                host="db01.internal",
            )
            for i in range(10)
        ]
        db_session.commit()
        run_detection(db_session)
        db_session.commit()

        second = run_detection(db_session)
        db_session.commit()

        # Stable, not silent: no new Alert gets created either run, but
        # since no Alert row is ever persisted for the cross-rule-duplicate
        # finding itself, there's no stored fingerprint for it to match
        # against on a later, separate run — so anomalous_event_volume's
        # finding is correctly re-classified as a cross-rule duplicate
        # again rather than silently vanishing. Documented, not a bug: the
        # invariant that actually matters — no duplicate Alert rows — holds
        # either way.
        assert second.alerts_created == 0
        assert second.duplicates_skipped >= 1  # ssh_brute_force's own re-run
        assert second.cross_rule_duplicates_skipped == 1

        alerts = db_session.scalars(select(Alert)).all()
        assert len(alerts) == 1


class TestDetectionMetrics:
    def test_rule_firing_and_duration_are_recorded(self, db_session, make_event):
        for i in range(10):
            make_event(
                SourceType.AUTH,
                NOW + timedelta(seconds=i * 20),
                {
                    "event_result": "failure",
                    "username": "admin",
                    "source_ip": "198.51.100.1",
                    "dest_host": "db01.internal",
                    "auth_method": "password",
                },
            )
        db_session.commit()

        alerts_before = alerts_created_total.labels(rule_key="ssh_brute_force")._value.get()
        duration_before = detection_rule_duration_seconds.labels(
            rule_key="ssh_brute_force"
        )._sum.get()

        run_detection(db_session)
        db_session.commit()

        assert alerts_created_total.labels(rule_key="ssh_brute_force")._value.get() == (
            alerts_before + 1
        )
        assert (
            detection_rule_duration_seconds.labels(rule_key="ssh_brute_force")._sum.get()
            >= duration_before
        )

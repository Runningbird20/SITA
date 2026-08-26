import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.metrics import (
    alerts_created_total,
    alerts_duplicate_skipped_total,
    detection_rule_duration_seconds,
)
from app.detection.base import compute_alert_fingerprint
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

        assert report.rules_run == 7
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

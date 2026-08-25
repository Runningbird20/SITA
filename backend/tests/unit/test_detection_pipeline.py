from datetime import UTC, datetime, timedelta

from sqlalchemy import select

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

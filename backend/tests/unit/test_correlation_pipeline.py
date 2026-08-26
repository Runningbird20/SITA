from sqlalchemy import select

from app.correlation.pipeline import run_correlation
from app.detection.pipeline import run_detection
from app.ioc.pipeline import run_ioc_extraction
from app.models.enums import IncidentStatus
from app.models.incident import Incident


class TestRunCorrelation:
    def test_single_alert_creates_new_incident(self, db_session, brute_force_events):
        brute_force_events("198.51.100.1", "db01.internal")
        db_session.commit()
        run_detection(db_session)
        db_session.commit()

        report = run_correlation(db_session)
        db_session.commit()

        assert report.incidents_created == 1
        assert report.incidents_joined == 0
        incident = db_session.scalars(select(Incident)).one()
        assert incident.status == IncidentStatus.OPEN
        assert "SSH Brute Force" in incident.title

    def test_alerts_sharing_ip_and_close_in_time_merge(self, db_session, brute_force_events):
        # Same source IP hitting two different hosts close together in time
        # shares an IOC (the attacker IP) -> should merge into one incident.
        brute_force_events("198.51.100.1", "db01.internal", base_offset=0)
        brute_force_events("198.51.100.1", "app02.internal", base_offset=600)
        db_session.commit()
        run_detection(db_session)
        db_session.commit()
        run_ioc_extraction(db_session)
        db_session.commit()

        report = run_correlation(db_session)
        db_session.commit()

        assert report.incidents_created == 1
        assert report.incidents_joined == 1
        assert len(db_session.scalars(select(Incident)).all()) == 1

    def test_alerts_far_apart_in_time_with_no_shared_signal_stay_separate(
        self, db_session, brute_force_events
    ):
        brute_force_events("198.51.100.1", "db01.internal", base_offset=0)
        brute_force_events("198.51.100.2", "app02.internal", base_offset=6 * 3600)
        db_session.commit()
        run_detection(db_session)
        db_session.commit()

        report = run_correlation(db_session)
        db_session.commit()

        assert report.incidents_created == 2
        assert report.incidents_joined == 0
        assert len(db_session.scalars(select(Incident)).all()) == 2

    def test_closed_incident_is_not_rejoined(self, db_session, brute_force_events):
        brute_force_events("198.51.100.1", "db01.internal", base_offset=0)
        db_session.commit()
        run_detection(db_session)
        db_session.commit()
        run_correlation(db_session)
        db_session.commit()

        incident = db_session.scalars(select(Incident)).one()
        incident.status = IncidentStatus.CLOSED
        db_session.commit()

        # A second, clearly-related burst (same IP, close in time) arrives
        # after the incident was closed by an analyst.
        brute_force_events("198.51.100.1", "db01.internal", base_offset=300)
        db_session.commit()
        run_detection(db_session)
        db_session.commit()

        report = run_correlation(db_session)
        db_session.commit()

        assert report.incidents_created == 1
        incidents = db_session.scalars(select(Incident)).all()
        assert len(incidents) == 2
        statuses = {i.status for i in incidents}
        assert statuses == {IncidentStatus.CLOSED, IncidentStatus.OPEN}

    def test_rerunning_does_not_reprocess_already_correlated_alerts(
        self, db_session, brute_force_events
    ):
        brute_force_events("198.51.100.1", "db01.internal")
        db_session.commit()
        run_detection(db_session)
        db_session.commit()

        first = run_correlation(db_session)
        db_session.commit()
        second = run_correlation(db_session)
        db_session.commit()

        assert first.alerts_processed >= 1
        assert second.alerts_processed == 0

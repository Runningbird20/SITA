from datetime import UTC, datetime, timedelta

from app.detection.pipeline import run_detection
from app.ioc.pipeline import run_ioc_extraction
from app.models.enums import SourceType

NOW = datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC)


class TestRunIOCExtraction:
    def test_extracts_and_links_events(self, db_session, make_event):
        make_event(
            SourceType.NETWORK,
            NOW,
            {
                "src_ip": "185.220.101.5",
                "src_port": 40000,
                "dst_ip": "10.0.0.5",
                "dst_port": 443,
                "protocol": "tcp",
            },
        )
        db_session.commit()

        report = run_ioc_extraction(db_session)
        db_session.commit()

        assert report.events_scanned == 1
        assert report.iocs_created >= 1
        assert report.iocs_by_type.get("ipv4", 0) >= 1

    def test_since_filters_older_events(self, db_session, make_event):
        make_event(
            SourceType.NETWORK,
            NOW,
            {
                "src_ip": "185.220.101.5",
                "src_port": 1,
                "dst_ip": "10.0.0.5",
                "dst_port": 443,
                "protocol": "tcp",
            },
        )
        db_session.commit()

        report = run_ioc_extraction(db_session, since=NOW + timedelta(days=1))
        assert report.events_scanned == 0
        assert report.iocs_created == 0

    def test_rerunning_does_not_duplicate_iocs(self, db_session, make_event):
        make_event(
            SourceType.NETWORK,
            NOW,
            {
                "src_ip": "185.220.101.5",
                "src_port": 1,
                "dst_ip": "10.0.0.5",
                "dst_port": 443,
                "protocol": "tcp",
            },
        )
        db_session.commit()

        first = run_ioc_extraction(db_session)
        db_session.commit()
        second = run_ioc_extraction(db_session)
        db_session.commit()

        assert first.iocs_created >= 1
        assert second.iocs_created == 0
        assert second.iocs_updated >= 1

    def test_alert_ioc_rollup_after_detection(self, db_session, make_event):
        # A brute-force pattern that both triggers ssh_brute_force (Phase 3)
        # and carries an extractable IP (Phase 4) — proves the two phases
        # compose: IOCs from an alert's matched events roll up onto the alert.
        for i in range(10):
            make_event(
                SourceType.AUTH,
                NOW + timedelta(seconds=i * 20),
                {
                    "event_result": "failure",
                    "username": "admin",
                    "source_ip": "185.220.101.5",
                    "dest_host": "db01.internal",
                    "auth_method": "password",
                },
            )
        db_session.commit()

        run_detection(db_session)
        db_session.commit()

        report = run_ioc_extraction(db_session)
        db_session.commit()

        assert report.alert_links_created >= 1

    def test_rollup_is_a_noop_when_no_alerts_exist(self, db_session, make_event):
        make_event(
            SourceType.NETWORK,
            NOW,
            {
                "src_ip": "185.220.101.5",
                "src_port": 1,
                "dst_ip": "10.0.0.5",
                "dst_port": 443,
                "protocol": "tcp",
            },
        )
        db_session.commit()

        report = run_ioc_extraction(db_session)
        assert report.alert_links_created == 0

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.detection import cli
from app.models import Base
from app.models.enums import SourceType
from app.models.event import SecurityEvent

NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


class TestDetectionCli:
    def test_main_runs_detection_and_prints_report(self, monkeypatch, capsys):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        test_session_local = sessionmaker(bind=engine)
        monkeypatch.setattr(cli, "SessionLocal", test_session_local)

        with test_session_local() as db:
            for i in range(10):
                db.add(
                    SecurityEvent(
                        source_type=SourceType.AUTH,
                        occurred_at=NOW + timedelta(seconds=i * 20),
                        ingested_at=NOW,
                        source_host="db01.internal",
                        raw_payload={},
                        normalized={
                            "event_result": "failure",
                            "username": "admin",
                            "source_ip": "198.51.100.1",
                            "dest_host": "db01.internal",
                            "auth_method": "password",
                        },
                    )
                )
            db.commit()

        exit_code = cli.main([])
        assert exit_code == 0

        output = capsys.readouterr().out
        assert '"ssh_brute_force": 1' in output

    def test_since_argument_is_parsed(self, monkeypatch):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        test_session_local = sessionmaker(bind=engine)
        monkeypatch.setattr(cli, "SessionLocal", test_session_local)

        exit_code = cli.main(["--since", "2026-01-15T00:00:00Z"])
        assert exit_code == 0

from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ioc import cli
from app.models import Base
from app.models.enums import SourceType
from app.models.event import SecurityEvent

NOW = datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC)


class TestIOCCli:
    def test_main_runs_extraction_and_prints_report(self, monkeypatch, capsys):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        test_session_local = sessionmaker(bind=engine)
        monkeypatch.setattr(cli, "SessionLocal", test_session_local)

        with test_session_local() as db:
            db.add(
                SecurityEvent(
                    source_type=SourceType.NETWORK,
                    occurred_at=NOW,
                    ingested_at=NOW,
                    source_host="fw01.internal",
                    raw_payload={},
                    normalized={
                        "src_ip": "185.220.101.5",
                        "src_port": 1,
                        "dst_ip": "10.0.0.5",
                        "dst_port": 443,
                        "protocol": "tcp",
                    },
                )
            )
            db.commit()

        exit_code = cli.main([])
        assert exit_code == 0

        output = capsys.readouterr().out
        assert '"events_scanned": 1' in output

    def test_since_argument_is_parsed(self, monkeypatch):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        test_session_local = sessionmaker(bind=engine)
        monkeypatch.setattr(cli, "SessionLocal", test_session_local)

        exit_code = cli.main(["--since", "2026-01-15T00:00:00Z"])
        assert exit_code == 0

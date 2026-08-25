from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base
from app.triage import cli

NOW = datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC)


class TestTriageCli:
    def test_main_runs_triage_and_prints_report(self, monkeypatch, capsys):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        test_session_local = sessionmaker(bind=engine)
        monkeypatch.setattr(cli, "SessionLocal", test_session_local)

        exit_code = cli.main([])
        assert exit_code == 0

        output = capsys.readouterr().out
        assert '"incidents_processed": 0' in output

    def test_since_argument_is_parsed(self, monkeypatch):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        test_session_local = sessionmaker(bind=engine)
        monkeypatch.setattr(cli, "SessionLocal", test_session_local)

        exit_code = cli.main(["--since", "2026-01-15T00:00:00Z"])
        assert exit_code == 0

    def test_incident_id_argument_is_parsed(self, monkeypatch):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        test_session_local = sessionmaker(bind=engine)
        monkeypatch.setattr(cli, "SessionLocal", test_session_local)

        exit_code = cli.main(["--incident-id", "00000000-0000-0000-0000-000000000000"])
        assert exit_code == 0

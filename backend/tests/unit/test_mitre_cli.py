from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.mitre import cli
from app.models import Base


class TestMitreCli:
    def test_main_loads_techniques_and_prints_reports(self, monkeypatch, capsys):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        test_session_local = sessionmaker(bind=engine)
        monkeypatch.setattr(cli, "SessionLocal", test_session_local)

        exit_code = cli.main([])
        assert exit_code == 0

        output = capsys.readouterr().out
        assert '"techniques_created"' in output
        assert '"alert_technique_mappings_created"' in output

    def test_since_argument_is_parsed(self, monkeypatch):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        test_session_local = sessionmaker(bind=engine)
        monkeypatch.setattr(cli, "SessionLocal", test_session_local)

        exit_code = cli.main(["--since", "2026-01-15T00:00:00Z"])
        assert exit_code == 0

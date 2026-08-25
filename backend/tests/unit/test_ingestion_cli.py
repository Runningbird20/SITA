import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.ingestion import cli
from app.models import Base
from app.models.enums import SourceType
from app.models.event import SecurityEvent


@pytest.fixture
def temp_jsonl_file(tmp_path):
    path = tmp_path / "events.jsonl"
    lines = [
        json.dumps(
            {
                "timestamp": "2026-01-15T03:10:00Z",
                "host": "web01.internal",
                "event_result": "failure",
                "username": "root",
                "source_ip": "203.0.113.7",
                "auth_method": "password",
            }
        ),
        "",
        json.dumps(
            {
                "timestamp": "2026-01-15T03:10:15Z",
                "host": "web01.internal",
                "event_result": "success",
                "username": "root",
                "source_ip": "203.0.113.7",
                "auth_method": "password",
            }
        ),
    ]
    path.write_text("\n".join(lines) + "\n")
    return path


class TestLoadJsonl:
    def test_skips_blank_lines(self, temp_jsonl_file):
        assert len(cli.load_jsonl(temp_jsonl_file)) == 2


class TestRunImport:
    def test_assigns_shared_batch_id_and_persists(self, temp_jsonl_file, monkeypatch):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        test_session_local = sessionmaker(bind=engine)
        monkeypatch.setattr(cli, "SessionLocal", test_session_local)

        report = cli.run_import(SourceType.AUTH, temp_jsonl_file)

        assert report.accepted == 2
        assert report.rejected == 0
        assert report.batch_id is not None

        with test_session_local() as db:
            events = db.scalars(select(SecurityEvent)).all()
            assert len(events) == 2
            assert all(e.ingestion_batch_id == report.batch_id for e in events)

    def test_main_returns_nonzero_exit_on_rejection(self, tmp_path, monkeypatch):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        test_session_local = sessionmaker(bind=engine)
        monkeypatch.setattr(cli, "SessionLocal", test_session_local)

        path = tmp_path / "bad.jsonl"
        path.write_text(json.dumps({"timestamp": "not-a-timestamp", "host": "x"}) + "\n")

        exit_code = cli.main([SourceType.DNS.value, str(path)])
        assert exit_code == 1

    def test_main_returns_zero_exit_when_all_accepted(self, temp_jsonl_file, monkeypatch):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        test_session_local = sessionmaker(bind=engine)
        monkeypatch.setattr(cli, "SessionLocal", test_session_local)

        exit_code = cli.main([SourceType.AUTH.value, str(temp_jsonl_file)])
        assert exit_code == 0

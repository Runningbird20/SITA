import uuid

from sqlalchemy import select

from app.core.metrics import events_ingested_total, ingestion_errors_total
from app.ingestion.service import ingest_records
from app.models.enums import SourceType
from app.models.event import SecurityEvent


class TestIngestRecords:
    def test_mixed_batch_accepts_valid_and_reports_invalid(self, db_session):
        records = [
            {
                "timestamp": "2026-01-15T03:10:00Z",
                "host": "web01.internal",
                "event_result": "failure",
                "username": "root",
                "source_ip": "203.0.113.7",
                "auth_method": "password",
            },
            {
                # missing source_ip
                "timestamp": "2026-01-15T03:10:15Z",
                "host": "web01.internal",
                "event_result": "failure",
                "username": "root",
                "auth_method": "password",
            },
            {
                "timestamp": "2026-01-15T03:10:30Z",
                "host": "web01.internal",
                "event_result": "success",
                "username": "root",
                "source_ip": "203.0.113.7",
                "auth_method": "password",
            },
        ]
        batch_id = uuid.uuid4()

        report = ingest_records(
            db=db_session, source_type=SourceType.AUTH, raw_records=records, batch_id=batch_id
        )

        assert report.total == 3
        assert report.accepted == 2
        assert report.rejected == 1
        assert report.errors[0].index == 1
        assert report.errors[0].field == "source_ip"

        db_session.commit()
        persisted = db_session.scalars(
            select(SecurityEvent).where(SecurityEvent.ingestion_batch_id == batch_id)
        ).all()
        assert len(persisted) == 2
        assert all(e.source_type == SourceType.AUTH for e in persisted)

    def test_no_batch_id_for_streaming_path(self, db_session):
        records = [
            {
                "timestamp": "2026-01-15T07:00:01Z",
                "host": "web01.internal",
                "method": "GET",
                "path": "/",
                "status_code": 200,
                "source_ip": "10.0.0.1",
            }
        ]
        report = ingest_records(
            db=db_session, source_type=SourceType.WEB, raw_records=records, batch_id=None
        )
        assert report.batch_id is None
        assert report.accepted == 1

        db_session.commit()
        persisted = db_session.scalars(select(SecurityEvent)).all()
        assert persisted[0].ingestion_batch_id is None

    def test_all_rejected_persists_nothing(self, db_session):
        records = [{"timestamp": "not-a-timestamp", "host": "x"}]
        report = ingest_records(
            db=db_session, source_type=SourceType.DNS, raw_records=records, batch_id=None
        )
        assert report.accepted == 0
        assert report.rejected == 1

        db_session.commit()
        assert db_session.scalars(select(SecurityEvent)).all() == []


class TestIngestionMetrics:
    def test_accepted_and_rejected_counts_are_recorded(self, db_session):
        events_before = events_ingested_total.labels(source_type="endpoint")._value.get()
        errors_before = ingestion_errors_total.labels(source_type="endpoint")._value.get()

        records = [
            {
                "timestamp": "2026-01-15T03:10:00Z",
                "host": "ws-01.internal",
                "process_name": "cmd.exe",
                "command_line": '"cmd.exe"',
                "pid": 100,
                "user": "svc-01",
            },
            {"timestamp": "not-a-timestamp"},
        ]
        ingest_records(db=db_session, source_type=SourceType.ENDPOINT, raw_records=records)

        assert (
            events_ingested_total.labels(source_type="endpoint")._value.get() == events_before + 1
        )
        assert (
            ingestion_errors_total.labels(source_type="endpoint")._value.get() == errors_before + 1
        )

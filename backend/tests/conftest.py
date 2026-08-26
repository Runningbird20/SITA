import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.models import Base
from app.models.enums import SourceType
from app.models.event import SecurityEvent

# The one canonical "trips exactly the ssh_brute_force rule" timestamp/
# event-burst fixture, shared by every test that just needs a single real
# alert to exist rather than a specific detection scenario. Previously
# duplicated near-identically across test_correlation_pipeline.py,
# test_mitre_pipeline.py, and test_triage_pipeline.py — consolidated here
# per TODO.md's Phase 11 "reusable synthetic fixtures" task.
BRUTE_FORCE_NOW = datetime(2026, 1, 15, 3, 0, 0, tzinfo=UTC)

# Resolves TODO.md's [[postgres-vs-sqlite]] open question: the default,
# every-developer-machine path stays SQLite in-memory (fast, hermetic, zero
# external dependency) — completely unchanged. When TEST_POSTGRES_URL is
# set, every test using db_session runs against that Postgres instead,
# each wrapped in a rolled-back transaction for isolation. Deliberately a
# *different* variable from DATABASE_URL/Settings.database_url (which the
# app itself reads) so a developer's normal .env can never accidentally
# point the test suite at a real database — this only activates when
# explicitly and separately opted into (see .github/workflows/ci.yml).
_TEST_POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")
_postgres_engine = create_engine(_TEST_POSTGRES_URL) if _TEST_POSTGRES_URL else None
if _postgres_engine is not None:
    Base.metadata.create_all(_postgres_engine)


@pytest.fixture
def db_session():
    """A session isolated per test. SQLite in-memory by default (foreign-key
    enforcement turned on, off by default in SQLite, so FK-integrity tests
    are meaningful); against real Postgres when TEST_POSTGRES_URL is set,
    via a SAVEPOINT-backed transaction so a test's own db_session.commit()
    calls never escape the per-test rollback.
    """
    if _postgres_engine is not None:
        connection = _postgres_engine.connect()
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        yield session
        session.close()
        transaction.rollback()
        connection.close()
        return

    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    engine.dispose()


@pytest.fixture
def make_event(db_session):
    """Factory for constructing a persisted SecurityEvent directly, bypassing
    the Phase 2 ingestion adapters — used by detection-rule tests that want
    precise control over event fields without re-testing ingestion.
    """

    def _make(source_type, occurred_at, normalized, host="test-host.internal"):
        security_event = SecurityEvent(
            source_type=source_type,
            occurred_at=occurred_at,
            ingested_at=occurred_at,
            source_host=host,
            raw_payload=dict(normalized),
            normalized=normalized,
        )
        db_session.add(security_event)
        db_session.flush()
        return security_event

    return _make


@pytest.fixture
def brute_force_events(make_event):
    """10 failed AUTH attempts from one source IP against one host within
    ssh_brute_force's default 300s window — the one canonical single-alert
    fixture shared across correlation/mitre/triage pipeline tests that just
    need a real Alert to exist. Returns the list of created SecurityEvents.
    """

    def _make(source_ip="198.51.100.1", dest_host="db01.internal", base_offset=0):
        return [
            make_event(
                SourceType.AUTH,
                BRUTE_FORCE_NOW + timedelta(seconds=base_offset + i * 20),
                {
                    "event_result": "failure",
                    "username": "admin",
                    "source_ip": source_ip,
                    "dest_host": dest_host,
                    "auth_method": "password",
                },
                host=dest_host,
            )
            for i in range(10)
        ]

    return _make

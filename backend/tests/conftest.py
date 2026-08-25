import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.models import Base
from app.models.event import SecurityEvent


@pytest.fixture
def db_session():
    """In-memory SQLite session with foreign-key enforcement turned on
    (off by default in SQLite) so FK-integrity tests are meaningful.
    """
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

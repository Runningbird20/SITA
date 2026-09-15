import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.live_updates import stream as stream_module
from app.live_updates.stream import new_incidents_since, stream_new_incidents, to_sse_event
from app.models import Base
from app.models.enums import IncidentStatus, Severity
from app.models.incident import Incident

NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


def _make_incident(db_session, created_at, title="Test Incident"):
    incident = Incident(
        title=title,
        status=IncidentStatus.OPEN,
        severity=Severity.HIGH,
        first_activity_at=created_at,
        last_activity_at=created_at,
        correlation_method={},
        created_at=created_at,
    )
    db_session.add(incident)
    db_session.flush()
    return incident


class TestNewIncidentsSince:
    def test_returns_incidents_created_after_the_cutoff(self, db_session):
        _make_incident(db_session, NOW - timedelta(minutes=5), title="Old")
        newer = _make_incident(db_session, NOW + timedelta(minutes=1), title="New")

        results = new_incidents_since(db_session, NOW)

        assert [i.id for i in results] == [newer.id]

    def test_returns_empty_when_nothing_new(self, db_session):
        _make_incident(db_session, NOW - timedelta(minutes=5))
        assert new_incidents_since(db_session, NOW) == []

    def test_orders_by_created_at(self, db_session):
        second = _make_incident(db_session, NOW + timedelta(minutes=2), title="Second")
        first = _make_incident(db_session, NOW + timedelta(minutes=1), title="First")

        results = new_incidents_since(db_session, NOW)

        assert [i.id for i in results] == [first.id, second.id]


class TestToSseEvent:
    def test_formats_as_a_valid_sse_event(self, db_session):
        incident = _make_incident(db_session, NOW, title="SSH Brute Force")

        event = to_sse_event(incident)

        assert event.startswith("event: incident_created\n")
        assert event.endswith("\n\n")
        data_line = [line for line in event.splitlines() if line.startswith("data: ")][0]
        payload = json.loads(data_line[len("data: ") :])
        assert payload["incident_id"] == str(incident.id)
        assert payload["title"] == "SSH Brute Force"
        assert payload["severity"] == "high"


class _FakeRequest:
    """Disconnects after `disconnect_after` polls — lets the otherwise
    infinite stream_new_incidents() loop terminate deterministically in a
    test instead of running forever.
    """

    def __init__(self, disconnect_after: int):
        self.disconnect_after = disconnect_after
        self.polls = 0

    async def is_disconnected(self) -> bool:
        self.polls += 1
        return self.polls > self.disconnect_after


class TestStreamNewIncidents:
    @pytest.fixture
    def isolated_session_factory(self, monkeypatch):
        engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        monkeypatch.setattr(stream_module, "SessionLocal", session_factory)
        yield session_factory
        engine.dispose()

    async def test_yields_an_event_for_an_incident_created_after_since(
        self, isolated_session_factory, monkeypatch
    ):
        monkeypatch.setattr(stream_module, "POLL_INTERVAL_SECONDS", 0)
        since = NOW
        with isolated_session_factory() as db:
            _make_incident(db, NOW + timedelta(seconds=1), title="New Incident")
            db.commit()

        events = [
            event async for event in stream_new_incidents(_FakeRequest(disconnect_after=1), since)
        ]

        assert len(events) == 1
        assert "New Incident" in events[0]

    async def test_stops_once_the_client_disconnects(self, isolated_session_factory, monkeypatch):
        monkeypatch.setattr(stream_module, "POLL_INTERVAL_SECONDS", 0)

        events = [
            event async for event in stream_new_incidents(_FakeRequest(disconnect_after=0), NOW)
        ]

        assert events == []

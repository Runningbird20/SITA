import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import get_db
from app.main import app
from app.models import Base
from app.models.event import SecurityEvent


@pytest.fixture
def client():
    # StaticPool: without it, each new connection to ":memory:" gets its own
    # fresh (tableless) database — the request thread would never see the
    # tables created below.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client, TestingSessionLocal
    app.dependency_overrides.clear()
    engine.dispose()


class TestIngestEventsEndpoint:
    def test_single_event_object_accepted(self, client):
        test_client, session_factory = client
        body = {
            "timestamp": "2026-01-15T03:10:00Z",
            "host": "web01.internal",
            "event_result": "failure",
            "username": "root",
            "source_ip": "203.0.113.7",
            "auth_method": "password",
        }
        response = test_client.post("/api/v1/events/auth", json=body)
        assert response.status_code == 201
        report = response.json()
        assert report["total"] == 1
        assert report["accepted"] == 1
        assert report["batch_id"] is None

        with session_factory() as db:
            events = db.scalars(select(SecurityEvent)).all()
            assert len(events) == 1
            assert events[0].normalized["username"] == "root"

    def test_array_body_with_one_invalid_record(self, client):
        test_client, _ = client
        body = [
            {
                "timestamp": "2026-01-15T07:00:01Z",
                "host": "web01.internal",
                "method": "GET",
                "path": "/",
                "status_code": 200,
                "source_ip": "10.0.0.1",
            },
            {
                "timestamp": "2026-01-15T07:00:05Z",
                "host": "web01.internal",
                "method": "TRACE",
                "path": "/",
                "status_code": 200,
                "source_ip": "10.0.0.1",
            },
        ]
        response = test_client.post("/api/v1/events/web", json=body)
        assert response.status_code == 201
        report = response.json()
        assert report["total"] == 2
        assert report["accepted"] == 1
        assert report["rejected"] == 1
        assert report["errors"][0]["index"] == 1
        assert report["errors"][0]["field"] == "method"

    def test_invalid_source_type_path_param_returns_422(self, client):
        test_client, _ = client
        response = test_client.post("/api/v1/events/not-a-real-source", json={})
        assert response.status_code == 422

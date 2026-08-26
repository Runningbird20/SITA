"""TODO.md Phase 11: 'Failure-case tests... (DB unavailable) confirming
graceful degradation, not crashes.' /healthz's except-branch (the DB is
unreachable) was the one piece of this project's own code with no test
covering it — closed here.
"""

from sqlalchemy.orm import Session


class TestHealthzDegradesWhenDatabaseIsUnavailable:
    def test_db_execute_failure_returns_200_degraded_not_a_crash(self, client, monkeypatch):
        test_client, _ = client

        def _raise(*_args, **_kwargs):
            raise ConnectionError("could not connect to server")

        monkeypatch.setattr(Session, "execute", _raise)

        response = test_client.get("/healthz")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "degraded"
        assert body["database"] == "unavailable"

    def test_healthy_database_still_reports_ok(self, client):
        test_client, _ = client
        response = test_client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "ok"}

"""Authentication, rate limiting, request body size cap, and security
headers. See DEF.md § Phase 14.
"""

from app.auth.service import create_user
from app.core.config import Settings
from app.models.enums import UserRole


def _create_analyst(session_factory, username="analyst1", password="correct-horse-battery"):
    with session_factory() as db:
        create_user(db, username, password, UserRole.ANALYST)
        db.commit()
    return username, password


def _login(test_client, username, password) -> str:
    response = test_client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["token"]


class TestAuthDisabledByDefault:
    def test_api_v1_route_works_with_no_users_configured_and_no_header(self, client):
        test_client, _ = client
        response = test_client.get("/api/v1/incidents")
        assert response.status_code == 200

    def test_health_and_metrics_never_require_auth_even_when_enabled(self, client):
        test_client, session_factory = client
        _create_analyst(session_factory)
        assert test_client.get("/healthz").status_code == 200
        assert test_client.get("/metrics").status_code == 200


class TestAuthEnabled:
    """Auth turns on the moment any User row exists — see
    app.auth.service.any_users_exist.
    """

    def test_missing_authorization_header_is_401(self, client):
        test_client, session_factory = client
        _create_analyst(session_factory)
        response = test_client.get("/api/v1/incidents")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"
        assert response.headers["WWW-Authenticate"] == "Bearer"

    def test_wrong_token_is_401(self, client):
        test_client, session_factory = client
        _create_analyst(session_factory)
        response = test_client.get(
            "/api/v1/incidents", headers={"Authorization": "Bearer wrong-token"}
        )
        assert response.status_code == 401

    def test_correct_token_is_authorized(self, client):
        test_client, session_factory = client
        username, password = _create_analyst(session_factory)
        token = _login(test_client, username, password)
        response = test_client.get(
            "/api/v1/incidents", headers={"Authorization": "Bearer " + token}
        )
        assert response.status_code == 200

    def test_wrong_password_is_401_at_login(self, client):
        test_client, session_factory = client
        username, _password = _create_analyst(session_factory)
        response = test_client.post(
            "/api/v1/auth/login", json={"username": username, "password": "not-it"}
        )
        assert response.status_code == 401

    def test_analyst_cannot_trigger_pipeline_run(self, client):
        test_client, session_factory = client
        username, password = _create_analyst(session_factory)
        token = _login(test_client, username, password)
        response = test_client.post(
            "/api/v1/pipeline/run", headers={"Authorization": "Bearer " + token}
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_admin_can_trigger_pipeline_run(self, client):
        test_client, session_factory = client
        with session_factory() as db:
            create_user(db, "admin1", "correct-horse-battery", UserRole.ADMIN)
            db.commit()
        token = _login(test_client, "admin1", "correct-horse-battery")
        response = test_client.post(
            "/api/v1/pipeline/run", headers={"Authorization": "Bearer " + token}
        )
        assert response.status_code == 200

    def test_analyst_cannot_trigger_reanalyze(self, client):
        test_client, session_factory = client
        username, password = _create_analyst(session_factory)
        token = _login(test_client, username, password)
        response = test_client.post(
            "/api/v1/pipeline/reanalyze", headers={"Authorization": "Bearer " + token}
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_admin_can_trigger_reanalyze(self, client):
        test_client, session_factory = client
        with session_factory() as db:
            create_user(db, "admin1", "correct-horse-battery", UserRole.ADMIN)
            db.commit()
        token = _login(test_client, "admin1", "correct-horse-battery")
        response = test_client.post(
            "/api/v1/pipeline/reanalyze", headers={"Authorization": "Bearer " + token}
        )
        assert response.status_code == 200

    def test_logout_revokes_the_token(self, client):
        test_client, session_factory = client
        username, password = _create_analyst(session_factory)
        token = _login(test_client, username, password)

        logout_response = test_client.post(
            "/api/v1/auth/logout", headers={"Authorization": "Bearer " + token}
        )
        assert logout_response.status_code == 204

        response = test_client.get(
            "/api/v1/incidents", headers={"Authorization": "Bearer " + token}
        )
        assert response.status_code == 401


class TestRateLimiting:
    def test_strict_tier_returns_429_with_retry_after_once_exceeded(self, client, monkeypatch):
        test_client, _ = client
        monkeypatch.setattr(
            "app.core.rate_limit.get_settings",
            lambda: Settings(rate_limit_strict_per_minute=3, rate_limit_general_per_minute=300),
        )
        record = {
            "timestamp": "2026-01-15T03:10:00Z",
            "host": "web01.internal",
            "event_result": "success",
            "username": "root",
            "source_ip": "203.0.113.7",
            "auth_method": "password",
        }
        for _ in range(3):
            response = test_client.post("/api/v1/events/auth", json=record)
            assert response.status_code == 201

        blocked = test_client.post("/api/v1/events/auth", json=record)
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "rate_limited"
        assert "Retry-After" in blocked.headers

    def test_general_tier_is_independent_of_strict_tier(self, client, monkeypatch):
        test_client, _ = client
        monkeypatch.setattr(
            "app.core.rate_limit.get_settings",
            lambda: Settings(rate_limit_strict_per_minute=1, rate_limit_general_per_minute=300),
        )
        record = {
            "timestamp": "2026-01-15T03:10:00Z",
            "host": "web01.internal",
            "event_result": "success",
            "username": "root",
            "source_ip": "203.0.113.7",
            "auth_method": "password",
        }
        test_client.post("/api/v1/events/auth", json=record)
        blocked = test_client.post("/api/v1/events/auth", json=record)
        assert blocked.status_code == 429

        # A general-tier route is unaffected by the strict tier being exhausted.
        assert test_client.get("/api/v1/incidents").status_code == 200

    def test_health_and_metrics_are_never_rate_limited(self, client, monkeypatch):
        test_client, _ = client
        monkeypatch.setattr(
            "app.core.rate_limit.get_settings",
            lambda: Settings(rate_limit_general_per_minute=1, rate_limit_strict_per_minute=1),
        )
        for _ in range(5):
            assert test_client.get("/healthz").status_code == 200


class TestRequestBodySizeCap:
    def test_oversized_body_is_rejected_before_processing(self, client, monkeypatch):
        test_client, _ = client
        monkeypatch.setattr("app.main.get_settings", lambda: Settings(max_request_body_bytes=10))
        response = test_client.post(
            "/api/v1/events/auth", json={"timestamp": "2026-01-15T03:10:00Z", "host": "x"}
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "payload_too_large"


class TestSecurityHeaders:
    def test_standard_headers_present_on_a_normal_response(self, client):
        test_client, _ = client
        response = test_client.get("/healthz")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert response.headers["Content-Security-Policy"] == "default-src 'none'"

    def test_headers_present_even_on_an_error_response(self, client):
        test_client, _ = client
        response = test_client.get("/api/v1/incidents/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404
        assert response.headers["X-Content-Type-Options"] == "nosniff"

    def test_csp_is_not_set_on_the_docs_page(self, client):
        test_client, _ = client
        response = test_client.get("/docs")
        assert "Content-Security-Policy" not in response.headers

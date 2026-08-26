"""Request-ID propagation, the /metrics endpoint, the catch-all error
handler, and /healthz's LLM-reachability field. See DEF.md § Phase 13.
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.main import app


class TestRequestIdPropagation:
    def test_response_carries_a_generated_request_id_header(self, client):
        test_client, _ = client
        response = test_client.get("/healthz")
        assert response.status_code == 200
        assert response.headers["X-Request-ID"]

    def test_inbound_request_id_is_echoed_back_rather_than_replaced(self, client):
        test_client, _ = client
        response = test_client.get("/healthz", headers={"X-Request-ID": "caller-supplied-id"})
        assert response.headers["X-Request-ID"] == "caller-supplied-id"

    def test_two_requests_get_different_generated_ids(self, client):
        test_client, _ = client
        first = test_client.get("/healthz").headers["X-Request-ID"]
        second = test_client.get("/healthz").headers["X-Request-ID"]
        assert first != second

    def test_request_id_is_still_set_when_the_completion_log_line_is_emitted(self, client, caplog):
        """Regression test: the request ID must still be readable from the
        logging filter at the point 'request completed' is logged, not
        already reset — a real bug caught by running the server for real
        and reading its own JSON logs, not just asserting on the response.
        """
        test_client, _ = client
        with caplog.at_level("INFO", logger="app.main"):
            response = test_client.get("/healthz", headers={"X-Request-ID": "regression-check"})

        completed = [r for r in caplog.records if r.message == "request completed"]
        assert len(completed) == 1
        assert completed[0].request_id == "regression-check"
        assert response.headers["X-Request-ID"] == "regression-check"


class TestMetricsEndpoint:
    def test_returns_prometheus_text_exposition_format(self, client):
        test_client, _ = client
        response = test_client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        body = response.text
        # A metric this suite's own requests must have already incremented.
        assert "sita_http_requests_total" in body

    def test_reflects_a_request_made_just_before_it(self, client):
        test_client, _ = client
        test_client.get("/healthz")
        response = test_client.get("/metrics")
        body = response.text
        assert 'path_template="/healthz"' in body


class TestCatchAllErrorHandler:
    def test_unhandled_exception_returns_structured_500_not_a_crash(self, client, monkeypatch):
        test_client, _ = client

        def _raise(*_args, **_kwargs):
            raise RuntimeError("simulated unexpected failure")

        monkeypatch.setattr(Session, "execute", _raise)

        # This app instance's TestClient (from the `client` fixture) raises
        # server exceptions by default; build a second one over the same
        # app/overrides that instead returns the real HTTP response, the
        # way a real deployed server would.
        with TestClient(app, raise_server_exceptions=False) as no_raise_client:
            response = no_raise_client.get("/api/v1/incidents")

        assert response.status_code == 500
        assert response.json() == {
            "error": {
                "code": "internal_error",
                "message": "Internal server error",
                "details": None,
            }
        }


class TestHealthzLLMField:
    def test_mock_provider_reports_not_configured_without_a_network_call(self, client):
        test_client, _ = client
        response = test_client.get("/healthz")
        assert response.json()["llm"] == "not_configured"

    def test_ollama_configured_and_reachable_reports_ok(self, client, monkeypatch):
        test_client, _ = client
        monkeypatch.setattr(
            "app.api.health.get_settings",
            lambda: Settings(llm_provider="ollama", ollama_base_url="http://fake-ollama:11434"),
        )

        class _FakeResponse:
            def raise_for_status(self) -> None:
                return None

        monkeypatch.setattr("app.api.health.httpx.get", lambda *a, **k: _FakeResponse())

        response = test_client.get("/healthz")
        body = response.json()
        assert body["llm"] == "ok"
        assert body["status"] == "ok"

    def test_ollama_configured_but_unreachable_reports_unavailable_and_degrades(
        self, client, monkeypatch
    ):
        test_client, _ = client
        monkeypatch.setattr(
            "app.api.health.get_settings",
            lambda: Settings(
                llm_provider="ollama",
                ollama_base_url="http://127.0.0.1:1",  # nothing listens here
            ),
        )
        response = test_client.get("/healthz")
        body = response.json()
        assert body["llm"] == "unavailable"
        assert body["status"] == "degraded"

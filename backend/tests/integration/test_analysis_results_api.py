from tests.integration.conftest import seed_full_incident


class TestListAndGetAnalysisResults:
    def test_requires_exactly_one_scope_param(self, client):
        test_client, _ = client

        response = test_client.get("/api/v1/analysis-results")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_query_parameter"

    def test_both_scope_params_rejected(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        response = test_client.get(
            "/api/v1/analysis-results",
            params={"incident_id": ids["incident_id"], "alert_id": ids["alert_id"]},
        )
        assert response.status_code == 422

    def test_list_scoped_by_incident_id(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        response = test_client.get(
            "/api/v1/analysis-results", params={"incident_id": ids["incident_id"]}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["task_type"] == "incident_summary"

    def test_list_scoped_by_alert_id(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        # The fixture's one AnalysisResult is incident-scoped, not
        # alert-scoped, so this exercises the alert_id filter branch and
        # correctly finds nothing.
        response = test_client.get("/api/v1/analysis-results", params={"alert_id": ids["alert_id"]})
        assert response.status_code == 200
        assert response.json()["total"] == 0

    def test_filter_by_task_type(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        response = test_client.get(
            "/api/v1/analysis-results",
            params={"incident_id": ids["incident_id"], "task_type": "mitre_suggestion"},
        )
        assert response.json()["total"] == 0

    def test_get_by_id(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        response = test_client.get(f"/api/v1/analysis-results/{ids['analysis_result_id']}")
        assert response.status_code == 200
        assert response.json()["id"] == ids["analysis_result_id"]

    def test_get_missing_returns_404(self, client):
        test_client, _ = client
        response = test_client.get("/api/v1/analysis-results/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

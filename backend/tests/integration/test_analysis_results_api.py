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


class TestAnalysisFeedback:
    def test_casting_a_vote_creates_feedback(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        response = test_client.put(
            f"/api/v1/analysis-results/{ids['analysis_result_id']}/feedback",
            json={"rating": "up"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["rating"] == "up"
        assert body["analysis_result_id"] == ids["analysis_result_id"]

        get_response = test_client.get(f"/api/v1/analysis-results/{ids['analysis_result_id']}")
        assert get_response.json()["feedback"]["rating"] == "up"

    def test_recasting_a_vote_overwrites_rather_than_duplicates(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        first = test_client.put(
            f"/api/v1/analysis-results/{ids['analysis_result_id']}/feedback",
            json={"rating": "up"},
        )
        second = test_client.put(
            f"/api/v1/analysis-results/{ids['analysis_result_id']}/feedback",
            json={"rating": "down"},
        )
        assert second.status_code == 200
        assert second.json()["rating"] == "down"
        # Same feedback row, not a new one.
        assert second.json()["id"] == first.json()["id"]

    def test_vote_on_missing_analysis_result_returns_404(self, client):
        test_client, _ = client
        response = test_client.put(
            "/api/v1/analysis-results/00000000-0000-0000-0000-000000000000/feedback",
            json={"rating": "up"},
        )
        assert response.status_code == 404

    def test_invalid_rating_rejected(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        response = test_client.put(
            f"/api/v1/analysis-results/{ids['analysis_result_id']}/feedback",
            json={"rating": "sideways"},
        )
        assert response.status_code == 422

    def test_clearing_a_vote_removes_it(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        test_client.put(
            f"/api/v1/analysis-results/{ids['analysis_result_id']}/feedback",
            json={"rating": "up"},
        )
        delete_response = test_client.delete(
            f"/api/v1/analysis-results/{ids['analysis_result_id']}/feedback"
        )
        assert delete_response.status_code == 204

        get_response = test_client.get(f"/api/v1/analysis-results/{ids['analysis_result_id']}")
        assert get_response.json()["feedback"] is None

    def test_clearing_a_never_cast_vote_is_a_no_op(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        response = test_client.delete(
            f"/api/v1/analysis-results/{ids['analysis_result_id']}/feedback"
        )
        assert response.status_code == 204

    def test_clear_on_missing_analysis_result_returns_404(self, client):
        test_client, _ = client
        response = test_client.delete(
            "/api/v1/analysis-results/00000000-0000-0000-0000-000000000000/feedback"
        )
        assert response.status_code == 404

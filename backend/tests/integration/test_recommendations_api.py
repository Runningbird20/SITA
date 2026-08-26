from tests.integration.conftest import seed_full_incident


class TestListAndGetRecommendations:
    def test_list_returns_paginated_envelope(self, client):
        test_client, session_factory = client
        seed_full_incident(session_factory)

        response = test_client.get("/api/v1/recommendations")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["source"] == "llm"

    def test_filter_by_status_and_priority(self, client):
        test_client, session_factory = client
        seed_full_incident(session_factory)

        response = test_client.get("/api/v1/recommendations", params={"status": "dismissed"})
        assert response.json()["total"] == 0

        response = test_client.get(
            "/api/v1/recommendations", params={"status": "open", "priority": "high"}
        )
        assert response.json()["total"] == 1

    def test_filter_by_incident_id(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        response = test_client.get(
            "/api/v1/recommendations", params={"incident_id": ids["incident_id"]}
        )
        assert response.json()["total"] == 1

    def test_filter_by_alert_id(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        # The fixture's recommendation is incident-scoped, not alert-scoped.
        response = test_client.get("/api/v1/recommendations", params={"alert_id": ids["alert_id"]})
        assert response.json()["total"] == 0

    def test_filter_by_source(self, client):
        test_client, session_factory = client
        seed_full_incident(session_factory)

        response = test_client.get("/api/v1/recommendations", params={"source": "rule_based"})
        assert response.json()["total"] == 0

        response = test_client.get("/api/v1/recommendations", params={"source": "llm"})
        assert response.json()["total"] == 1

    def test_get_by_id(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        response = test_client.get(f"/api/v1/recommendations/{ids['recommendation_id']}")
        assert response.status_code == 200
        assert response.json()["id"] == ids["recommendation_id"]

    def test_get_missing_returns_404(self, client):
        test_client, _ = client
        response = test_client.get("/api/v1/recommendations/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

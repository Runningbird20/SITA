from tests.integration.conftest import seed_full_incident


class TestListAndGetMitreTechniques:
    def test_list_returns_paginated_envelope(self, client):
        test_client, session_factory = client
        seed_full_incident(session_factory)

        response = test_client.get("/api/v1/mitre-techniques")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["technique_id"] == "T1110.001"

    def test_filter_by_tactic(self, client):
        test_client, session_factory = client
        seed_full_incident(session_factory)

        response = test_client.get("/api/v1/mitre-techniques", params={"tactic": "discovery"})
        assert response.json()["total"] == 0

        response = test_client.get(
            "/api/v1/mitre-techniques", params={"tactic": "credential-access"}
        )
        assert response.json()["total"] == 1

    def test_get_by_id(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        response = test_client.get(f"/api/v1/mitre-techniques/{ids['technique_id']}")
        assert response.status_code == 200
        assert response.json()["technique_id"] == "T1110.001"

    def test_get_missing_returns_404(self, client):
        test_client, _ = client
        response = test_client.get("/api/v1/mitre-techniques/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

from tests.integration.conftest import seed_full_incident


class TestListAndGetDetections:
    def test_list_returns_paginated_envelope(self, client):
        test_client, session_factory = client
        seed_full_incident(session_factory)

        response = test_client.get("/api/v1/detections")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["rule_key"] == "ssh_brute_force"

    def test_filter_by_category_and_enabled(self, client):
        test_client, session_factory = client
        seed_full_incident(session_factory)

        response = test_client.get("/api/v1/detections", params={"category": "network"})
        assert response.json()["total"] == 0

        response = test_client.get(
            "/api/v1/detections", params={"category": "authentication", "enabled": True}
        )
        assert response.json()["total"] == 1

    def test_get_detail_includes_mitre_techniques(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        response = test_client.get(f"/api/v1/detections/{ids['detection_id']}")
        assert response.status_code == 200
        body = response.json()
        assert len(body["mitre_techniques"]) == 1
        assert body["mitre_techniques"][0]["technique_id"] == "T1110.001"

    def test_get_missing_returns_404(self, client):
        test_client, _ = client
        response = test_client.get("/api/v1/detections/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

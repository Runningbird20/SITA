from tests.integration.conftest import seed_full_incident


class TestListAndGetAlerts:
    def test_list_returns_paginated_envelope(self, client):
        test_client, session_factory = client
        seed_full_incident(session_factory)

        response = test_client.get("/api/v1/alerts")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["severity"] == "high"

    def test_filter_by_severity(self, client):
        test_client, session_factory = client
        seed_full_incident(session_factory)

        response = test_client.get("/api/v1/alerts", params={"severity": "low"})
        assert response.status_code == 200
        assert response.json()["total"] == 0

    def test_filter_by_rule_key(self, client):
        test_client, session_factory = client
        seed_full_incident(session_factory)

        response = test_client.get("/api/v1/alerts", params={"rule_key": "ssh_brute_force"})
        assert response.status_code == 200
        assert response.json()["total"] == 1

        response = test_client.get("/api/v1/alerts", params={"rule_key": "nonexistent_rule"})
        assert response.json()["total"] == 0

    def test_filter_by_incident_id(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        response = test_client.get("/api/v1/alerts", params={"incident_id": ids["incident_id"]})
        assert response.json()["total"] == 1

    def test_get_by_id(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        response = test_client.get(f"/api/v1/alerts/{ids['alert_id']}")
        assert response.status_code == 200
        assert response.json()["id"] == ids["alert_id"]

    def test_get_missing_returns_404(self, client):
        test_client, _ = client
        response = test_client.get("/api/v1/alerts/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_mitre_techniques_endpoint(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        response = test_client.get(f"/api/v1/alerts/{ids['alert_id']}/mitre-techniques")
        assert response.status_code == 200
        mappings = response.json()
        assert len(mappings) == 1
        assert mappings[0]["source"] == "rule"
        assert mappings[0]["technique"]["technique_id"] == "T1110.001"

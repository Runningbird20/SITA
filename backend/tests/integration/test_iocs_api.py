from tests.integration.conftest import seed_full_incident


class TestListAndGetIocs:
    def test_list_returns_paginated_envelope(self, client):
        test_client, session_factory = client
        seed_full_incident(session_factory)

        response = test_client.get("/api/v1/iocs")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["value"] == "198.51.100.1"

    def test_filter_by_type(self, client):
        test_client, session_factory = client
        seed_full_incident(session_factory)

        response = test_client.get("/api/v1/iocs", params={"ioc_type": "domain"})
        assert response.json()["total"] == 0

        response = test_client.get("/api/v1/iocs", params={"ioc_type": "ipv4"})
        assert response.json()["total"] == 1

    def test_filter_by_min_confidence(self, client):
        test_client, session_factory = client
        seed_full_incident(session_factory)

        response = test_client.get("/api/v1/iocs", params={"min_confidence": 0.95})
        assert response.json()["total"] == 0

        response = test_client.get("/api/v1/iocs", params={"min_confidence": 0.5})
        assert response.json()["total"] == 1

    def test_get_by_id(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        response = test_client.get(f"/api/v1/iocs/{ids['ioc_id']}")
        assert response.status_code == 200
        assert response.json()["id"] == ids["ioc_id"]

    def test_get_missing_returns_404(self, client):
        test_client, _ = client
        response = test_client.get("/api/v1/iocs/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

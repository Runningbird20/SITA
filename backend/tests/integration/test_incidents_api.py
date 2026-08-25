from tests.integration.conftest import seed_full_incident


class TestListAndGetIncidents:
    def test_list_returns_paginated_envelope(self, client):
        test_client, session_factory = client
        seed_full_incident(session_factory)

        response = test_client.get("/api/v1/incidents")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["status"] == "open"

    def test_filter_by_status_and_severity(self, client):
        test_client, session_factory = client
        seed_full_incident(session_factory)

        response = test_client.get("/api/v1/incidents", params={"status": "closed"})
        assert response.json()["total"] == 0

        response = test_client.get("/api/v1/incidents", params={"severity": "high"})
        assert response.json()["total"] == 1

    def test_get_detail_includes_nested_objects(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        response = test_client.get(f"/api/v1/incidents/{ids['incident_id']}")
        assert response.status_code == 200
        body = response.json()

        assert len(body["alerts"]) == 1
        assert body["alerts"][0]["id"] == ids["alert_id"]

        assert len(body["iocs"]) == 1
        assert body["iocs"][0]["id"] == ids["ioc_id"]

        assert len(body["analysis_results"]) == 1
        assert body["analysis_results"][0]["id"] == ids["analysis_result_id"]

        assert len(body["recommendations"]) == 1
        assert body["recommendations"][0]["id"] == ids["recommendation_id"]

        assert len(body["mitre_techniques"]) == 1
        technique_entry = body["mitre_techniques"][0]
        assert technique_entry["technique_id"] == "T1110.001"
        assert technique_entry["sources"] == ["rule"]
        assert len(technique_entry["evidence"]) == 1
        assert technique_entry["evidence"][0]["confidence"] is None

    def test_get_missing_returns_404(self, client):
        test_client, _ = client
        response = test_client.get("/api/v1/incidents/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_standalone_mitre_techniques_endpoint_matches_nested_field(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        detail = test_client.get(f"/api/v1/incidents/{ids['incident_id']}").json()
        standalone = test_client.get(
            f"/api/v1/incidents/{ids['incident_id']}/mitre-techniques"
        ).json()

        assert standalone == detail["mitre_techniques"]

    def test_invalid_sort_field_returns_422(self, client):
        test_client, _ = client
        response = test_client.get("/api/v1/incidents", params={"sort": "severity"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_query_parameter"

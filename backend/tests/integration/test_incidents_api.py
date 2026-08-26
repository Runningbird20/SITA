import uuid
from datetime import timedelta

from app.models.analysis_result import AnalysisResult
from app.models.enums import AnalysisTaskType, AnalysisValidationStatus
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
        assert body["items"][0]["alert_count"] == 1

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

        assert body["alert_count"] == 1
        assert len(body["alerts"]) == 1
        assert body["alerts"][0]["id"] == ids["alert_id"]

        assert len(body["iocs"]) == 1
        assert body["iocs"][0]["id"] == ids["ioc_id"]
        assert body["iocs"][0]["alert_ids"] == [ids["alert_id"]]

        assert len(body["entities"]) == 1
        assert body["entities"][0]["id"] == ids["entity_id"]
        assert body["entities"][0]["identifier"] == "db01.internal"

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

    def test_detail_shows_only_the_latest_analysis_result_per_task_type(self, client):
        """Regression test: run_triage(..., force=True) adds a new
        AnalysisResult row rather than replacing an old one (by design,
        for auditability) — the incident detail's AI panel must show only
        the latest per task_type, not a stale/invalid earlier one ahead
        of it. Found live, on a real incident with more than one triage
        run behind it.
        """
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        with session_factory() as db:
            older = db.get(AnalysisResult, uuid.UUID(ids["analysis_result_id"]))
            newer = AnalysisResult(
                incident_id=uuid.UUID(ids["incident_id"]),
                task_type=AnalysisTaskType.INCIDENT_SUMMARY,
                provider="ollama",
                model="CyberCrew/notmythos-8b",
                prompt_version="v1",
                raw_output='{"summary": "real summary", "key_points": []}',
                parsed_output={"summary": "real summary", "key_points": []},
                validation_status=AnalysisValidationStatus.VALID,
                confidence=1.0,
                latency_ms=500,
                created_at=older.created_at + timedelta(minutes=5),
            )
            db.add(newer)
            db.commit()
            newer_id = str(newer.id)

        response = test_client.get(f"/api/v1/incidents/{ids['incident_id']}")
        body = response.json()
        summaries = [r for r in body["analysis_results"] if r["task_type"] == "incident_summary"]
        assert len(summaries) == 1
        assert summaries[0]["id"] == newer_id
        assert summaries[0]["validation_status"] == "valid"

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

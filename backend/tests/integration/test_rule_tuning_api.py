from datetime import UTC, datetime

from app.models.alert import Alert
from app.models.detection import Detection
from app.models.enums import AlertStatus, DetectionCategory, Severity
from tests.integration.conftest import seed_full_incident

NOW = datetime(2026, 1, 15, 3, 0, 0, tzinfo=UTC)


def _seed_high_false_positive_rate_rule(session_factory, count=10, false_positive_count=6):
    with session_factory() as db:
        detection = Detection(
            rule_key="ssh_brute_force",
            name="SSH Brute Force",
            description="Repeated auth failures.",
            category=DetectionCategory.AUTHENTICATION,
            default_severity=Severity.HIGH,
            enabled=True,
            config={"failure_threshold": 10},
        )
        db.add(detection)
        db.flush()
        for i in range(count):
            status = AlertStatus.FALSE_POSITIVE if i < false_positive_count else AlertStatus.NEW
            db.add(
                Alert(
                    detection_id=detection.id,
                    fingerprint=f"fp-{i}",
                    severity=Severity.HIGH,
                    confidence=0.8,
                    status=status,
                    rationale="test",
                    severity_factors={},
                    first_event_at=NOW,
                    last_event_at=NOW,
                )
            )
        db.commit()
        return detection.id


class TestSetAlertStatus:
    def test_updates_status(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        response = test_client.put(
            f"/api/v1/alerts/{ids['alert_id']}/status", json={"status": "false_positive"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "false_positive"

    def test_persists_and_is_audited(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        test_client.put(f"/api/v1/alerts/{ids['alert_id']}/status", json={"status": "resolved"})

        response = test_client.get(f"/api/v1/alerts/{ids['alert_id']}")
        assert response.json()["status"] == "resolved"

    def test_missing_alert_returns_404(self, client):
        test_client, _ = client
        response = test_client.put(
            "/api/v1/alerts/00000000-0000-0000-0000-000000000000/status",
            json={"status": "resolved"},
        )
        assert response.status_code == 404

    def test_invalid_status_returns_422(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        response = test_client.put(
            f"/api/v1/alerts/{ids['alert_id']}/status", json={"status": "not_a_real_status"}
        )
        assert response.status_code == 422


class TestTuningSuggestions:
    def test_returns_suggestion_for_high_false_positive_rule(self, client):
        test_client, session_factory = client
        _seed_high_false_positive_rate_rule(session_factory)

        response = test_client.get("/api/v1/detections/tuning-suggestions")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["rule_key"] == "ssh_brute_force"
        assert body[0]["threshold_key"] == "failure_threshold"
        assert body[0]["suggested_threshold_value"] == 12

    def test_empty_when_no_rule_has_enough_feedback(self, client):
        test_client, session_factory = client
        seed_full_incident(session_factory)

        response = test_client.get("/api/v1/detections/tuning-suggestions")
        assert response.status_code == 200
        assert response.json() == []

    def test_route_not_shadowed_by_detection_id_path_param(self, client):
        test_client, _ = client
        response = test_client.get("/api/v1/detections/tuning-suggestions")
        assert response.status_code == 200


class TestUpdateDetectionConfig:
    def test_merges_config_partially(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        response = test_client.patch(
            f"/api/v1/detections/{ids['detection_id']}/config",
            json={"config": {"failure_threshold": 12}},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["config"]["failure_threshold"] == 12

        get_response = test_client.get(f"/api/v1/detections/{ids['detection_id']}")
        assert get_response.json()["config"]["failure_threshold"] == 12

    def test_missing_detection_returns_404(self, client):
        test_client, _ = client
        response = test_client.patch(
            "/api/v1/detections/00000000-0000-0000-0000-000000000000/config",
            json={"config": {"failure_threshold": 12}},
        )
        assert response.status_code == 404

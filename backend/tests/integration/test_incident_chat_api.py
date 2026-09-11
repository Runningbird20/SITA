from tests.integration.conftest import seed_full_incident


class TestPostIncidentChat:
    def test_asks_a_question_and_gets_a_reply(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        response = test_client.post(
            f"/api/v1/incidents/{ids['incident_id']}/chat",
            json={"message": "What happened here?"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["role"] == "assistant"
        assert body["incident_id"] == ids["incident_id"]
        assert body["content"]

    def test_missing_incident_returns_404(self, client):
        test_client, _ = client
        response = test_client.post(
            "/api/v1/incidents/00000000-0000-0000-0000-000000000000/chat",
            json={"message": "Hello?"},
        )
        assert response.status_code == 404

    def test_empty_message_returns_422(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        response = test_client.post(
            f"/api/v1/incidents/{ids['incident_id']}/chat", json={"message": ""}
        )
        assert response.status_code == 422


class TestGetIncidentChat:
    def test_returns_full_thread_in_order(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        test_client.post(
            f"/api/v1/incidents/{ids['incident_id']}/chat", json={"message": "First question?"}
        )
        test_client.post(
            f"/api/v1/incidents/{ids['incident_id']}/chat", json={"message": "Second question?"}
        )

        response = test_client.get(f"/api/v1/incidents/{ids['incident_id']}/chat")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 4
        assert [m["role"] for m in body] == ["user", "assistant", "user", "assistant"]
        assert body[0]["content"] == "First question?"
        assert body[2]["content"] == "Second question?"

    def test_empty_thread_for_an_incident_with_no_chat_yet(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)

        response = test_client.get(f"/api/v1/incidents/{ids['incident_id']}/chat")
        assert response.status_code == 200
        assert response.json() == []

    def test_missing_incident_returns_404(self, client):
        test_client, _ = client
        response = test_client.get("/api/v1/incidents/00000000-0000-0000-0000-000000000000/chat")
        assert response.status_code == 404

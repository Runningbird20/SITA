from sqlalchemy import select

from app.models.event import SecurityEvent


class TestIngestEventsEndpoint:
    def test_single_event_object_accepted(self, client):
        test_client, session_factory = client
        body = {
            "timestamp": "2026-01-15T03:10:00Z",
            "host": "web01.internal",
            "event_result": "failure",
            "username": "root",
            "source_ip": "203.0.113.7",
            "auth_method": "password",
        }
        response = test_client.post("/api/v1/events/auth", json=body)
        assert response.status_code == 201
        report = response.json()
        assert report["total"] == 1
        assert report["accepted"] == 1
        assert report["batch_id"] is None

        with session_factory() as db:
            events = db.scalars(select(SecurityEvent)).all()
            assert len(events) == 1
            assert events[0].normalized["username"] == "root"

    def test_array_body_with_one_invalid_record(self, client):
        test_client, _ = client
        body = [
            {
                "timestamp": "2026-01-15T07:00:01Z",
                "host": "web01.internal",
                "method": "GET",
                "path": "/",
                "status_code": 200,
                "source_ip": "10.0.0.1",
            },
            {
                "timestamp": "2026-01-15T07:00:05Z",
                "host": "web01.internal",
                "method": "TRACE",
                "path": "/",
                "status_code": 200,
                "source_ip": "10.0.0.1",
            },
        ]
        response = test_client.post("/api/v1/events/web", json=body)
        assert response.status_code == 201
        report = response.json()
        assert report["total"] == 2
        assert report["accepted"] == 1
        assert report["rejected"] == 1
        assert report["errors"][0]["index"] == 1
        assert report["errors"][0]["field"] == "method"

    def test_invalid_source_type_path_param_returns_422(self, client):
        test_client, _ = client
        response = test_client.post("/api/v1/events/not-a-real-source", json={})
        assert response.status_code == 422


class TestListAndGetEvents:
    def _seed(self, test_client):
        test_client.post(
            "/api/v1/events/auth",
            json={
                "timestamp": "2026-01-15T03:10:00Z",
                "host": "web01.internal",
                "event_result": "failure",
                "username": "root",
                "source_ip": "203.0.113.7",
                "auth_method": "password",
            },
        )
        test_client.post(
            "/api/v1/events/web",
            json={
                "timestamp": "2026-01-15T07:00:01Z",
                "host": "web01.internal",
                "method": "GET",
                "path": "/",
                "status_code": 200,
                "source_ip": "10.0.0.1",
            },
        )

    def test_list_returns_paginated_envelope(self, client):
        test_client, _ = client
        self._seed(test_client)

        response = test_client.get("/api/v1/events")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert body["limit"] == 50
        assert body["offset"] == 0
        assert len(body["items"]) == 2

    def test_filter_by_source_type(self, client):
        test_client, _ = client
        self._seed(test_client)

        response = test_client.get("/api/v1/events", params={"source_type": "auth"})
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["source_type"] == "auth"

    def test_pagination_limit(self, client):
        test_client, _ = client
        self._seed(test_client)

        response = test_client.get("/api/v1/events", params={"limit": 1})
        body = response.json()
        assert body["total"] == 2
        assert len(body["items"]) == 1

    def test_get_by_id(self, client):
        test_client, _ = client
        self._seed(test_client)
        event_id = test_client.get("/api/v1/events").json()["items"][0]["id"]

        response = test_client.get(f"/api/v1/events/{event_id}")
        assert response.status_code == 200
        assert response.json()["id"] == event_id

    def test_get_missing_returns_structured_404(self, client):
        test_client, _ = client
        response = test_client.get("/api/v1/events/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404
        body = response.json()
        assert body["error"]["code"] == "not_found"

    def test_invalid_sort_field_returns_422(self, client):
        test_client, _ = client
        response = test_client.get("/api/v1/events", params={"sort": "not_a_field"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_query_parameter"

    def test_invalid_limit_returns_structured_422(self, client):
        test_client, _ = client
        response = test_client.get("/api/v1/events", params={"limit": 0})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

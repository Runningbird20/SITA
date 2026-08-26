"""POST /auth/login, /auth/logout, /auth/me, /auth/users (admin-only),
GET /audit-log (admin-only). See DEF.md § Phase 14, "Multi-user / RBAC
(post-roadmap)". Missing-Authorization / wrong-token / role-gating cases
for the endpoints themselves are covered in test_security_api.py — this
file covers the auth/audit-log resources' own request/response shapes.
"""

from sqlalchemy import select

from app.auth.service import create_user
from app.models.enums import UserRole
from app.models.user import User
from tests.integration.conftest import seed_full_incident


def _create_admin(session_factory, username="admin1", password="correct-horse-battery"):
    with session_factory() as db:
        create_user(db, username, password, UserRole.ADMIN)
        db.commit()
    return username, password


def _login(test_client, username, password) -> str:
    response = test_client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["token"]


class TestLogin:
    def test_login_returns_token_user_and_expiry(self, client):
        test_client, session_factory = client
        username, password = _create_admin(session_factory)

        response = test_client.post(
            "/api/v1/auth/login", json={"username": username, "password": password}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["token"]
        assert body["user"]["username"] == username
        assert body["user"]["role"] == "admin"
        assert "password" not in body["user"]
        assert "expires_at" in body

    def test_unknown_username_is_401(self, client):
        test_client, _ = client
        response = test_client.post(
            "/api/v1/auth/login", json={"username": "nobody", "password": "whatever"}
        )
        assert response.status_code == 401


class TestMe:
    def test_me_with_no_users_configured_returns_null(self, client):
        test_client, _ = client
        response = test_client.get("/api/v1/auth/me")
        assert response.status_code == 200
        assert response.json() is None

    def test_me_with_a_valid_token_returns_the_user(self, client):
        test_client, session_factory = client
        username, password = _create_admin(session_factory)
        token = _login(test_client, username, password)

        response = test_client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token})
        assert response.status_code == 200
        assert response.json()["username"] == username
        assert response.json()["role"] == "admin"


class TestUserManagement:
    def test_admin_can_create_a_new_user(self, client):
        test_client, session_factory = client
        _username, password = _create_admin(session_factory)
        token = _login(test_client, "admin1", password)

        response = test_client.post(
            "/api/v1/auth/users",
            json={"username": "analyst2", "password": "another-password", "role": "analyst"},
            headers={"Authorization": "Bearer " + token},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["username"] == "analyst2"
        assert body["role"] == "analyst"
        assert "password" not in body

    def test_analyst_cannot_create_a_new_user(self, client):
        test_client, session_factory = client
        with session_factory() as db:
            create_user(db, "analyst1", "correct-horse-battery", UserRole.ANALYST)
            db.commit()
        token = _login(test_client, "analyst1", "correct-horse-battery")

        response = test_client.post(
            "/api/v1/auth/users",
            json={"username": "analyst2", "password": "another-password", "role": "analyst"},
            headers={"Authorization": "Bearer " + token},
        )
        assert response.status_code == 403

    def test_admin_can_list_users(self, client):
        test_client, session_factory = client
        _username, password = _create_admin(session_factory)
        with session_factory() as db:
            create_user(db, "analyst1", "correct-horse-battery", UserRole.ANALYST)
            db.commit()
        token = _login(test_client, "admin1", password)

        response = test_client.get(
            "/api/v1/auth/users", headers={"Authorization": "Bearer " + token}
        )
        assert response.status_code == 200
        usernames = {u["username"] for u in response.json()}
        assert usernames == {"admin1", "analyst1"}


class TestAuditLog:
    def test_pipeline_run_and_feedback_actions_are_recorded(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)
        _username, password = _create_admin(session_factory)
        token = _login(test_client, "admin1", password)
        headers = {"Authorization": "Bearer " + token}

        test_client.post("/api/v1/pipeline/run", headers=headers)
        test_client.post("/api/v1/pipeline/reanalyze", headers=headers)
        test_client.put(
            f"/api/v1/analysis-results/{ids['analysis_result_id']}/feedback",
            json={"rating": "up"},
            headers=headers,
        )

        response = test_client.get("/api/v1/audit-log", headers=headers)
        assert response.status_code == 200
        actions = {row["action"] for row in response.json()["items"]}
        assert "pipeline.run" in actions
        assert "triage.reanalyze" in actions
        assert "feedback.set" in actions

    def test_filter_by_action(self, client):
        test_client, session_factory = client
        ids = seed_full_incident(session_factory)
        _username, password = _create_admin(session_factory)
        token = _login(test_client, "admin1", password)
        headers = {"Authorization": "Bearer " + token}

        test_client.post("/api/v1/pipeline/run", headers=headers)
        test_client.put(
            f"/api/v1/analysis-results/{ids['analysis_result_id']}/feedback",
            json={"rating": "up"},
            headers=headers,
        )

        response = test_client.get(
            "/api/v1/audit-log", params={"action": "feedback.set"}, headers=headers
        )
        assert response.status_code == 200
        actions = {row["action"] for row in response.json()["items"]}
        assert actions == {"feedback.set"}

    def test_filter_by_user_id(self, client):
        test_client, session_factory = client
        _username, password = _create_admin(session_factory)
        with session_factory() as db:
            admin_id = db.scalars(select(User.id).where(User.username == "admin1")).one()
        token = _login(test_client, "admin1", password)
        headers = {"Authorization": "Bearer " + token}

        test_client.post("/api/v1/pipeline/run", headers=headers)

        response = test_client.get(
            "/api/v1/audit-log", params={"user_id": str(admin_id)}, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["total"] >= 1
        assert all(row["user_id"] == str(admin_id) for row in response.json()["items"])

    def test_analyst_cannot_read_the_audit_log(self, client):
        test_client, session_factory = client
        with session_factory() as db:
            create_user(db, "analyst1", "correct-horse-battery", UserRole.ANALYST)
            db.commit()
        token = _login(test_client, "analyst1", "correct-horse-battery")

        response = test_client.get(
            "/api/v1/audit-log", headers={"Authorization": "Bearer " + token}
        )
        assert response.status_code == 403

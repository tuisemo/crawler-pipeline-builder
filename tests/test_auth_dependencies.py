"""Tests for authentication FastAPI dependencies.

Covers:
- get_current_user: extracts session cookie, validates session, returns user or raises 401
- require_auth: forces authentication on any route it's applied to
- require_task_access: checks task ownership, returns 404 if user doesn't own the task
"""

from __future__ import annotations

import pytest
import fakeredis
from fastapi.testclient import TestClient

from backend.auth.session import create_session, upsert_user
from backend.database import get_cursor, run_migrations
from server import app


@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    fake_r = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("backend.auth.redis_client.get_redis", lambda: fake_r)
    return fake_r


@pytest.fixture(autouse=True)
def _setup_auth_environment(monkeypatch: pytest.MonkeyPatch):
    """Prepare auth env vars and clean DB tables before each test."""
    monkeypatch.setenv("USER_CENTER_BASE_URI", "https://user-center.example.com")
    monkeypatch.setenv("USER_CENTER_CLIENT_ID", "crawler-client")
    monkeypatch.setenv("USER_CENTER_CLIENT_SECRET", "crawler-secret")
    monkeypatch.setenv("USER_CENTER_SCOPE", "basic")
    monkeypatch.setenv("USER_CENTER_REDIRECT_URI", "http://testserver/auth/callback")
    monkeypatch.delenv("ENV", raising=False)

    run_migrations()
    with get_cursor() as cur:
        cur.execute("DELETE FROM task_assets")
        cur.execute("DELETE FROM tasks")
        cur.execute("DELETE FROM users")


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def sample_user():
    return upsert_user(
        external_id="openId_testuser",
        display_name="Test User",
        email="test@example.com",
    )


@pytest.fixture()
def auth_headers(sample_user, monkeypatch):
    """Helper to authenticate requests with Authorization bearer header."""
    monkeypatch.setenv("SESSION_TTL_HOURS", "24")
    token = create_session(user_id=sample_user["id"])
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def expiring_auth_headers(sample_user, monkeypatch):
    monkeypatch.setenv("SESSION_TTL_HOURS", "24")
    token = create_session(
        user_id=sample_user["id"],
        access_token="expired-access",
        refresh_token="refresh-123",
        access_token_expires_at="2020-01-01T00:00:00+00:00",
    )
    return {"Authorization": f"Bearer {token}"}


# ── Public endpoint access ──────────────────────────────────────────


class TestPublicEndpoints:
    def test_index_is_public(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_auth_me_without_bearer_header_returns_401(self, client):
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_auth_me_refreshes_expired_session(self, client, expiring_auth_headers, monkeypatch):
        async def _refresh_access_token(refresh_token: str):
            assert refresh_token == "refresh-123"
            return {
                "access_token": "new-access",
                "refresh_token": "refresh-456",
                "expires_at": 4102444800,
            }

        monkeypatch.setattr(
            "backend.auth.dependencies.refresh_access_token",
            _refresh_access_token,
        )

        response = client.get("/api/auth/me", headers=expiring_auth_headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["data"]["auth"]["has_refresh_token"] is True


# ── Workflow routes require auth ────────────────────────────────────────


class TestWorkflowAuthRequired:
    @pytest.mark.parametrize(
        "endpoint,method,payload",
        [
            ("/api/workflows/validate", "post", {"graph": {"nodes": [{"id":"n1","type":"open_page","data":{"url":"http://a.com"}}], "edges": []}}),
        ],
    )
    def test_workflow_without_bearer_header_returns_401(self, client, endpoint, method, payload):
        response = client.post(endpoint, json=payload)
        assert response.status_code == 401

    def test_workflow_with_valid_bearer_header_authenticates(self, client, auth_headers):
        response = client.post(
            "/api/workflows/validate",
            json={"graph": {"nodes": [{"id":"n1","type":"open_page","data":{"url":"http://a.com"}}], "edges": []}},
            headers=auth_headers,
        )
        assert response.status_code != 401


# ── require_task_access ownership check ─────────────────────────────────


class TestTaskAccessControl:
    def test_ownership_check_logic(self, client, sample_user, auth_headers):
        # Insert a task owned by sample_user
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO tasks (owner_user_id, name) VALUES (%s, 'My Task')",
                (sample_user["id"],),
            )
            task_id = cur.lastrowid

        # Accessing as owner should work (not 401 or 404)
        response = client.get(f"/api/tasks/{task_id}", headers=auth_headers)
        assert response.status_code == 200

    def test_non_owner_receives_404(self, client, sample_user, auth_headers):
        # Create another user who owns a task
        other_user = upsert_user(external_id="other", display_name="Other")
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO tasks (owner_user_id, name) VALUES (%s, 'Other Task')",
                (other_user["id"],),
            )
            task_id = cur.lastrowid

        # Accessing as sample_user (non-owner) should return 404
        response = client.get(f"/api/tasks/{task_id}", headers=auth_headers)
        assert response.status_code == 404


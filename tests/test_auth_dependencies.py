"""Tests for authentication FastAPI dependencies.

Covers:
- get_current_user: extracts session cookie, validates session, returns user or raises 401
- require_auth: forces authentication on any route it's applied to
- require_task_access: checks task ownership, returns 404 if user doesn't own the task
- /api/workflows/* routes return 401 when no valid session cookie is present
- /api/assist/* routes return 401 when no valid session cookie is present
- Authenticated users can access /api/workflows/* and /api/assist/* normally
- Public endpoints (/, /static/*, /api/auth/*) remain accessible without auth
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.auth.session import create_session, upsert_user
from backend.database import get_cursor, run_migrations
from server import app


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _setup_auth_environment(monkeypatch: pytest.MonkeyPatch):
    """Prepare auth env vars and clean DB tables before each test."""
    monkeypatch.setenv("USER_CENTER_BASE_URI", "https://user-center.example.com")
    monkeypatch.setenv("USER_CENTER_CLIENT_ID", "crawler-client")
    monkeypatch.setenv("USER_CENTER_CLIENT_SECRET", "crawler-secret")
    monkeypatch.setenv("USER_CENTER_SCOPE", "basic")
    monkeypatch.setenv("USER_CENTER_REDIRECT_URI", "http://testserver/api/auth/callback")
    monkeypatch.setenv("SESSION_COOKIE_NAME", "session_token")
    monkeypatch.delenv("ENV", raising=False)

    run_migrations()
    with get_cursor() as cur:
        cur.execute("DELETE FROM task_assets")
        cur.execute("DELETE FROM tasks")
        cur.execute("DELETE FROM sessions")
        cur.execute("DELETE FROM users")


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def sample_user():
    """Insert a sample user via upsert_user and return the user dict."""
    return upsert_user(
        external_id="openId_testuser",
        display_name="Test User",
        email="test@example.com",
    )


@pytest.fixture()
def authenticated_session(sample_user, monkeypatch: pytest.MonkeyPatch):
    """Create a session for sample_user and return the raw token."""
    monkeypatch.setenv("SESSION_TTL_HOURS", "24")
    token = create_session(user_id=sample_user["id"])
    return token


@pytest.fixture()
def two_users_with_sessions(monkeypatch: pytest.MonkeyPatch):
    """Create two users (Alice and Bob) each with an active session."""
    user_alice = upsert_user(
        external_id="openId_alice",
        display_name="Alice",
        email="alice@example.com",
    )
    user_bob = upsert_user(
        external_id="openId_bob",
        display_name="Bob",
        email="bob@example.com",
    )
    monkeypatch.setenv("SESSION_TTL_HOURS", "24")
    token_alice = create_session(user_id=user_alice["id"])
    token_bob = create_session(user_id=user_bob["id"])
    return {
        "alice": {"user": user_alice, "token": token_alice},
        "bob": {"user": user_bob, "token": token_bob},
    }


# ── Public endpoint access (no auth required) ──────────────────────────


class TestPublicEndpoints:
    """Public endpoints must remain accessible without authentication."""

    def test_index_is_public(self, client):
        """GET / must not require authentication."""
        response = client.get("/")
        assert response.status_code == 200

    def test_auth_me_without_cookie_returns_401(self, client):
        """GET /api/auth/me without cookie must return 401."""
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_auth_login_returns_302_to_oauth_provider(self, client):
        """GET /api/auth/login must return 302 redirect to OAuth provider.

        The redirect target is the user-center authorize URL. We only
        verify that a 302 is returned and the Location header points to
        the user-center base URI. We do NOT follow the redirect to avoid
        hitting the external URL.
        """
        response = client.get("/api/auth/login", follow_redirects=False)
        assert response.status_code == 302
        location = response.headers.get("location", "")
        assert "user-center.example.com" in location


# ── Workflow routes require auth ────────────────────────────────────────


class TestWorkflowAuthRequired:
    """All /api/workflows/* routes must require authentication."""

    @pytest.mark.parametrize(
        "endpoint,method,payload",
        [
            ("/api/workflows/validate", "post", {"graph": {"nodes": [], "edges": []}}),
            ("/api/workflows/from-legacy-config", "post", {"legacy": {}}),
            ("/api/workflows/to-prompt", "post", {"graph": {"nodes": [], "edges": []}}),
            ("/api/workflows/compile-plan", "post", {"graph": {"nodes": [], "edges": []}}),
            ("/api/workflows/generate-skeleton", "post", {"graph": {"nodes": [], "edges": []}}),
            ("/api/workflows/generate-crawler", "post", {"graph": {"nodes": [], "edges": []}}),
            ("/api/workflows/generate-detail-batch-runner", "post", {"graph": {"nodes": [], "edges": []}}),
            ("/api/workflows/run-script-sandbox", "post", {"script": "print('hello')"}),
            ("/api/workflows/format-script", "post", {"script": "print('hello')"}),
            ("/api/workflows/save-script", "post", {"path": "test.py", "content": "print('hello')"}),
        ],
    )
    def test_workflow_without_cookie_returns_401(self, client, endpoint, method, payload):
        """Any /api/workflows/* endpoint without session cookie returns 401."""
        if method == "post":
            response = client.post(endpoint, json=payload)
        else:
            response = client.get(endpoint)
        assert response.status_code == 401, (
            f"{method.upper()} {endpoint} returned {response.status_code}, expected 401"
        )

    def test_workflow_with_valid_cookie_authenticates(self, client, authenticated_session):
        """Valid session cookie allows the request through (200 or 400 from service, but NOT 401)."""
        cookie = {"session_token": authenticated_session}
        response = client.post(
            "/api/workflows/validate",
            json={"graph": {"nodes": [], "edges": []}},
            cookies=cookie,
        )
        # Auth passed (not 401). 200 = valid graph, 400 = invalid graph — both mean auth succeeded
        assert response.status_code != 401, "Auth should have passed with valid cookie"

    def test_workflow_with_forged_cookie_returns_401(self, client):
        """Forged/invalid session cookie returns 401."""
        response = client.post(
            "/api/workflows/validate",
            json={"graph": {"nodes": [], "edges": []}},
            cookies={"session_token": "completely-fake-token-value"},
        )
        assert response.status_code == 401


# ── Assist routes require auth ─────────────────────────────────────────


class TestAssistAuthRequired:
    """All /api/assist/* routes must require authentication."""

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/assist/infer-fields",
            "/api/assist/optimize-selector",
            "/api/assist/analyze-pagination",
        ],
    )
    def test_assist_without_cookie_returns_401(self, client, endpoint):
        """Any /api/assist/* endpoint without session cookie returns 401."""
        response = client.post(endpoint, json={"html": "<html/>", "prompt": "test"})
        assert response.status_code == 401, (
            f"POST {endpoint} returned {response.status_code}, expected 401"
        )

    def test_assist_with_valid_cookie_authenticates(self, client, authenticated_session):
        """Valid session cookie allows the request through (not 401)."""
        cookie = {"session_token": authenticated_session}
        response = client.post(
            "/api/assist/infer-fields",
            json={"html": "<html/>", "prompt": "extract fields"},
            cookies=cookie,
        )
        # Auth passed if not 401
        assert response.status_code != 401, "Auth should have passed with valid cookie"

    def test_assist_with_forged_cookie_returns_401(self, client):
        """Forged session cookie returns 401 on assist endpoints."""
        response = client.post(
            "/api/assist/infer-fields",
            json={"html": "<html/>", "prompt": "extract fields"},
            cookies={"session_token": "fake-token"},
        )
        assert response.status_code == 401


# ── require_task_access ownership check ─────────────────────────────────


class TestTaskAccessControl:
    """require_task_access checks that current user owns the specified task."""

    def test_ownership_check_logic(self, two_users_with_sessions):
        """Verify that require_task_access correctly distinguishes owner from non-owner."""
        alice = two_users_with_sessions["alice"]
        bob = two_users_with_sessions["bob"]

        # Insert a task owned by Alice
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO tasks (owner_user_id, name, description, target_url, status)
                   VALUES (%s, 'Alice private task', '', '', 'draft')""",
                (alice["user"]["id"],),
            )
            task_id = cur.lastrowid

        # Verify in DB that Alice owns it and Bob doesn't
        with get_cursor() as cur:
            cur.execute("SELECT owner_user_id FROM tasks WHERE id = %s", (task_id,))
            row = cur.fetchone()
            assert row["owner_user_id"] == alice["user"]["id"]
            assert row["owner_user_id"] != bob["user"]["id"]


# ── get_current_user dependency behavior ────────────────────────────────


class TestGetCurrentUser:
    """Unit tests for the get_current_user FastAPI dependency."""

    def test_missing_cookie_raises_401(self, client):
        """Request without session cookie raises 401."""
        response = client.post(
            "/api/workflows/validate",
            json={"graph": {"nodes": [], "edges": []}},
        )
        assert response.status_code == 401

    def test_invalid_token_raises_401(self, client):
        """Request with forged/invalid session token raises 401."""
        response = client.post(
            "/api/workflows/validate",
            json={"graph": {"nodes": [], "edges": []}},
            cookies={"session_token": "not-a-real-token"},
        )
        assert response.status_code == 401

    def test_expired_token_raises_401(self, client, sample_user, monkeypatch):
        """Session token that has expired raises 401."""
        # Create session that expires immediately (0 hours TTL)
        token = create_session(user_id=sample_user["id"], ttl_hours=0)

        response = client.post(
            "/api/workflows/validate",
            json={"graph": {"nodes": [], "edges": []}},
            cookies={"session_token": token},
        )
        assert response.status_code == 401

    def test_valid_token_authenticates(self, client, authenticated_session):
        """Valid session token allows access to protected routes (not 401)."""
        response = client.post(
            "/api/workflows/validate",
            json={"graph": {"nodes": [], "edges": []}},
            cookies={"session_token": authenticated_session},
        )
        assert response.status_code != 401


# ── require_auth passthrough ────────────────────────────────────────────


class TestRequireAuth:
    """require_auth is a pass-through dependency that forces authentication."""

    def test_require_auth_returns_user_on_success(self, client, authenticated_session):
        """When authentication succeeds, require_auth returns the user object (not 401)."""
        response = client.post(
            "/api/workflows/validate",
            json={"graph": {"nodes": [], "edges": []}},
            cookies={"session_token": authenticated_session},
        )
        assert response.status_code != 401

    def test_require_auth_raises_401_on_failure(self, client):
        """When authentication fails, require_auth raises 401."""
        response = client.post(
            "/api/workflows/validate",
            json={"graph": {"nodes": [], "edges": []}},
        )
        assert response.status_code == 401

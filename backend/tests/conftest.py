"""Shared test configuration.

CRITICAL: All tests use a SEPARATE database (crawler_workflow_test) to avoid
destroying production/development data.  The test database name is forced via
DB_NAME env var override before any backend module is imported by pytest.
"""

from __future__ import annotations

import pytest
import fakeredis

from database import get_cursor, ensure_schema

# ── Test database isolation ───────────────────────────────────────────────

_TEST_DB_NAME = "crawler_workflow_test"


@pytest.fixture(autouse=True, scope="session")
def _force_test_database():
    """Override DB_NAME so every test connects to a separate test database.

    This runs once per session and MUST execute before any backend module
    that calls ``get_settings()`` at import time.
    """
    import os
    os.environ["DB_NAME"] = _TEST_DB_NAME
    # Reset the lazy connection pool so it picks up the new DB_NAME
    from database import db as _db
    _db._pool = None
    yield
    # Teardown: close pool
    from database import close_connection
    close_connection()


@pytest.fixture(autouse=True)
def _clean_tables():
    """DELETE all rows from business tables before each test.

    Runs against the test database only (guaranteed by _force_test_database).
    """
    ensure_schema()
    with get_cursor() as cur:
        cur.execute("DELETE FROM task_assets")
        cur.execute("DELETE FROM tasks")
        cur.execute("DELETE FROM users")


@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    """Replace the real Redis client with fakeredis."""
    fake_r = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("auth.redis_client.get_redis", lambda: fake_r)
    return fake_r


@pytest.fixture(autouse=True)
def _setup_auth_environment(monkeypatch: pytest.MonkeyPatch):
    """Provide sane auth env vars for every test."""
    monkeypatch.setenv("USER_CENTER_BASE_URI", "https://user-center.example.com")
    monkeypatch.setenv("USER_CENTER_CLIENT_ID", "crawler-client")
    monkeypatch.setenv("USER_CENTER_CLIENT_SECRET", "crawler-secret")
    monkeypatch.setenv("USER_CENTER_SCOPE", "basic")
    monkeypatch.setenv("USER_CENTER_REDIRECT_URI", "http://testserver/api/auth/callback")
    monkeypatch.setenv("USER_CENTER_FRONTEND_URL", "http://testserver")
    monkeypatch.delenv("ENV", raising=False)


# ── Reusable fixtures ─────────────────────────────────────────────────────


@pytest.fixture()
def client():
    """FastAPI TestClient (no auth)."""
    from fastapi.testclient import TestClient
    from app import app
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def test_user():
    """Create a test user + session token and return dict."""
    from auth.session import create_session, upsert_user
    user = upsert_user(
        external_id="openId_testuser",
        display_name="Test User",
        email="test@example.com",
    )
    token = create_session(user_id=user["id"])
    return {"user": user, "token": token}


@pytest.fixture()
def auth_client(test_user):
    """FastAPI TestClient with Authorization header pre-set."""
    from fastapi.testclient import TestClient
    from app import app
    token = test_user["token"]
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as c:
        yield c

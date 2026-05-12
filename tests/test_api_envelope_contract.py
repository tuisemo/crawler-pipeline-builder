"""Tests for API response envelope contract (transport layer only).

These tests verify that all API responses use the same envelope structure
regardless of the underlying domain. They require authentication.
"""

from fastapi.testclient import TestClient

from backend.auth.session import create_session, upsert_user
from backend.database import get_cursor, run_migrations
from server import app


client = TestClient(app)


def _setup_auth(monkeypatch):
    """Set up authenticated session for tests that need auth."""
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
    user = upsert_user(
        external_id="envelope_test_user",
        display_name="Envelope Test User",
        email="envelope@test.com",
    )
    token = create_session(user_id=user["id"])
    return token


def _get_auth_cookie(token):
    return {"session_token": token}


def test_workflow_success_response_uses_transport_envelope_only(monkeypatch):
    """Workflow success response uses transport envelope."""
    token = _setup_auth(monkeypatch)
    response = client.post(
        "/api/workflows/validate",
        json={"graph": {"nodes": [{"id": "n1", "type": "open_page", "data": {"url": "http://example.com"}}], "edges": []}},
        cookies=_get_auth_cookie(token),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "success": True,
        "error_code": None,
        "error": None,
        "data": {"message": "Workflow is valid"},
        "warnings": [],
        "meta": {},
    }


def test_workflow_domain_fields_are_nested_under_data(monkeypatch):
    """Legacy config conversion response nests domain fields under data."""
    token = _setup_auth(monkeypatch)
    response = client.post(
        "/api/workflows/from-legacy-config",
        json={
            "url": "http://example.com",
            "item_selector": ".item",
            "fields": [{"name": "title", "selector": "h1", "type": "text"}],
        },
        cookies=_get_auth_cookie(token),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "graph" not in payload
    assert payload["data"]["graph"]["nodes"][0]["type"] == "open_page"


def test_validation_errors_use_the_same_envelope(monkeypatch):
    """Validation errors still use the same transport envelope."""
    token = _setup_auth(monkeypatch)
    response = client.post(
        "/api/workflows/validate",
        json={},
        cookies=_get_auth_cookie(token),
    )

    # Returns 422 because the auth dependency passes but Pydantic validation fails
    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["error_code"] == "request_validation_error"
    assert payload["data"] == {}
    assert payload["meta"]["detail"]

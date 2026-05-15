"""Tests for API response envelope contract (transport layer only).

These tests verify that all API responses use the same envelope structure
regardless of the underlying domain. They require authentication.
"""

from fastapi.testclient import TestClient

from backend.auth.session import create_session, upsert_user
from server import app

client = TestClient(app)


def _setup_auth(monkeypatch):
    """Set up authenticated session for tests that need auth."""
    user = upsert_user(
        external_id="envelope_test_user",
        display_name="Envelope Test User",
        email="envelope@test.com",
    )
    token = create_session(user_id=user["id"])
    return token


def _get_auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_workflow_success_response_uses_transport_envelope_only(monkeypatch):
    """Workflow success response uses transport envelope."""
    token = _setup_auth(monkeypatch)
    response = client.post(
        "/api/workflows/validate",
        json={"graph": {"nodes": [{"id": "n1", "type": "open_page", "data": {"url": "http://example.com"}}], "edges": []}},
        headers=_get_auth_headers(token),
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
    """Workflow compile-plan response nests domain fields under data."""
    token = _setup_auth(monkeypatch)
    response = client.post(
        "/api/workflows/compile-plan",
        json={
            "graph": {
                "nodes": [
                    {"id": "n1", "type": "open_page", "data": {"url": "http://example.com"}},
                    {"id": "n2", "type": "select_list", "data": {"item_selector": ".item"}},
                    {"id": "n3", "type": "extract_field", "data": {"fields": [{"name": "title", "selector": "h1", "type": "text"}]}},
                    {"id": "n4", "type": "emit_record", "data": {}},
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "n2"},
                    {"id": "e2", "source": "n2", "target": "n3"},
                    {"id": "e3", "source": "n3", "target": "n4"},
                ],
            },
        },
        headers=_get_auth_headers(token),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "entry_url" not in payload
    assert payload["data"]["plan"]["entry_url"] == "http://example.com"


def test_validation_errors_use_the_same_envelope(monkeypatch):
    """Validation errors still use the same transport envelope."""
    token = _setup_auth(monkeypatch)
    response = client.post(
        "/api/workflows/validate",
        json={},
        headers=_get_auth_headers(token),
    )

    # Returns 422 because the auth dependency passes but Pydantic validation fails
    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["error_code"] == "request_validation_error"
    assert payload["data"] == {}
    assert payload["meta"]["detail"]

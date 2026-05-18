"""Tests for auth API routes."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from auth.session import consume_oauth_state
from database import get_cursor
from app import app


def _extract_state(location: str) -> str:
    query = parse_qs(urlparse(location).query)
    return query["state"][0]


def _mock_user_center_success(monkeypatch: pytest.MonkeyPatch):
    async def _exchange_code_for_token(*, code: str, redirect_uri: str, code_verifier: str | None = None):
        assert code
        assert redirect_uri
        return {
            "access_token": "access-token-001",
            "refresh_token": "refresh-token-001",
            "expires_in": 3600,
            "name": "Auth Test User",
        }

    monkeypatch.setattr("api.auth_routes.exchange_code_for_token", _exchange_code_for_token)
    monkeypatch.setattr(
        "api.auth_routes.derive_local_user_profile_from_token",
        lambda token: {
            "external_id": "open-id-001",
            "display_name": token.get("name") or "Auth Test User",
            "email": "auth.user@example.com",
            "avatar_url": "https://example.com/avatar.png",
        },
    )


def _perform_login_callback(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _mock_user_center_success(monkeypatch)

    login_response = client.get("/api/auth/login", params={"next": "/dashboard"}, follow_redirects=False)
    assert login_response.status_code == 302
    state = _extract_state(login_response.headers["location"])
    callback_response = client.get(
        "/api/auth/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )
    return callback_response, state


def test_login_redirects_to_user_center_with_state(client: TestClient):
    response = client.get("/api/auth/login", params={"next": "/tasks/42"}, follow_redirects=False)

    assert response.status_code == 302
    location = response.headers["location"]
    parsed = urlparse(location)
    params = parse_qs(parsed.query)

    assert location.startswith("https://user-center.example.com/oauth/authorize")
    assert params["state"][0]
    assert "crawler_workflow_oauth_state=" in response.headers.get("set-cookie", "")
    payload = consume_oauth_state(params["state"][0])
    assert payload is not None
    assert payload["code_verifier"]


def test_callback_with_valid_state_redirects_to_frontend(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    response, _ = _perform_login_callback(client, monkeypatch)

    assert response.status_code == 302
    location = response.headers["location"]
    assert "sessionId=" in location
    assert "nextPath=" in location
    assert location.startswith("http://testserver/#/auth/callback")

    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS count FROM users")
        user_count = cur.fetchone()["count"]
    assert user_count == 1


def test_callback_rejects_missing_stable_subject(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    async def _exchange_code_for_token(*, code: str, redirect_uri: str, code_verifier: str | None = None):
        return {"access_token": "access-token-001", "expires_in": 3600, "name": "Auth Test User"}

    monkeypatch.setattr("api.auth_routes.exchange_code_for_token", _exchange_code_for_token)
    monkeypatch.setattr(
        "api.auth_routes.derive_local_user_profile_from_token",
        lambda token: {
            "external_id": None,
            "display_name": token.get("name") or "Auth Test User",
            "email": None,
            "avatar_url": None,
        },
    )

    login_response = client.get("/api/auth/login", params={"next": "/dashboard"}, follow_redirects=False)
    state = _extract_state(login_response.headers["location"])
    response = client.get(
        "/api/auth/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "error=oauth_subject_missing" in response.headers["location"]


def test_callback_redirect_uses_redirect_origin_when_frontend_url_missing(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("USER_CENTER_FRONTEND_URL", raising=False)
    monkeypatch.setattr("core.settings.load_env_config", lambda *args, **kwargs: {})
    response, _ = _perform_login_callback(client, monkeypatch)
    assert response.status_code == 302
    assert response.headers["location"].startswith("http://testserver/#/auth/callback")


def test_callback_redirect_uses_app_origin_when_redirect_uri_points_to_frontend_callback(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("USER_CENTER_FRONTEND_URL", raising=False)
    monkeypatch.setenv("USER_CENTER_REDIRECT_URI", "https://app.example.com/auth/callback")
    monkeypatch.setattr("core.settings.load_env_config", lambda *args, **kwargs: {})
    response, _ = _perform_login_callback(client, monkeypatch)
    assert response.status_code == 302
    assert response.headers["location"].startswith("https://app.example.com/#/auth/callback")


def test_callback_rejects_invalid_state(client: TestClient):
    response = client.get(
        "/api/auth/callback",
        params={"code": "valid-code", "state": "non-existent-state"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "error=invalid_oauth_state" in response.headers["location"]


def test_callback_consumes_state_once(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    response, state = _perform_login_callback(client, monkeypatch)
    assert response.status_code == 302

    second_response = client.get(
        "/api/auth/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )
    assert second_response.status_code == 302
    assert "error=invalid_oauth_state" in second_response.headers["location"]


def test_callback_rejects_state_from_different_client(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _mock_user_center_success(monkeypatch)

    login_response = client.get("/api/auth/login", params={"next": "/dashboard"}, follow_redirects=False)
    state = _extract_state(login_response.headers["location"])

    with TestClient(app) as other_client:
        callback_response = other_client.get(
            "/api/auth/callback",
            params={"code": "valid-code", "state": state},
            follow_redirects=False,
        )

    assert callback_response.status_code == 302
    assert "error=invalid_oauth_state" in callback_response.headers["location"]

    # Original client can still use the state (not consumed by the other client)
    valid_response = client.get(
        "/api/auth/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )
    assert valid_response.status_code == 302


def _extract_session_id_from_redirect(location: str) -> str:
    """Extract sessionId from the frontend callback redirect URL."""
    parsed = urlparse(location)
    # fragment is like #/auth/callback?sessionId=xxx&nextPath=/dashboard
    fragment = parsed.fragment
    query_part = fragment.split("?", 1)[1] if "?" in fragment else ""
    params = parse_qs(query_part)
    return params["sessionId"][0]


def test_me_returns_200_with_user_when_authenticated(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    response, _ = _perform_login_callback(client, monkeypatch)
    location = response.headers["location"]
    session_id = _extract_session_id_from_redirect(location)

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {session_id}"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["user"]["display_name"] == "Auth Test User"
    assert payload["data"]["auth"]["session_status"] == "active"
    assert payload["data"]["auth"]["has_refresh_token"] is True


def test_me_returns_401_without_bearer_header(client: TestClient):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_logout_deletes_session(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    response, _ = _perform_login_callback(client, monkeypatch)
    location = response.headers["location"]
    session_id = _extract_session_id_from_redirect(location)

    response = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {session_id}"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["loggedOut"] is True

    me_response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {session_id}"})
    assert me_response.status_code == 401


def test_logout_no_longer_returns_logout_uri_config(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    response, _ = _perform_login_callback(client, monkeypatch)
    session_id = _extract_session_id_from_redirect(response.headers["location"])

    monkeypatch.delenv("USER_CENTER_FRONTEND_URL", raising=False)
    monkeypatch.setenv("USER_CENTER_REDIRECT_URI", "https://app.example.com/auth/callback")
    monkeypatch.setattr("core.settings.load_env_config", lambda *args, **kwargs: {})

    response = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {session_id}"})
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["loggedOut"] is True
    # Logout no longer redirects to user-center; logoutUriConfig is absent
    assert "logoutUriConfig" not in payload


def test_logout_rejects_invalid_session(client: TestClient):
    response = client.post("/api/auth/logout", headers={"Authorization": "Bearer invalid-session"})
    assert response.status_code == 401


def test_login_sanitizes_external_next_path(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _mock_user_center_success(monkeypatch)

    login_response = client.get(
        "/api/auth/login",
        params={"next": "https://evil.com/steal"},
        follow_redirects=False,
    )
    state = _extract_state(login_response.headers["location"])

    callback_response = client.get(
        "/api/auth/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )
    assert callback_response.status_code == 302
    location = callback_response.headers["location"]
    assert "nextPath=%2F" in location


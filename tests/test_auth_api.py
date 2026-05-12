"""Tests for auth API routes.

Coverage:
- GET /api/auth/login redirect format with OAuth2 params
- GET /api/auth/callback valid/invalid state handling
- GET /api/auth/me authenticated and unauthenticated behavior
- POST /api/auth/logout session deletion + cookie clearing + logout URL payload
- Cookie attribute behavior (HttpOnly, SameSite=Lax, Path=/, Secure in production)
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from backend.auth.user_center import UserCenterServerError, UserDetails
from backend.database import get_cursor, run_migrations
from server import app


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


def _extract_state(location: str) -> str:
    query = parse_qs(urlparse(location).query)
    return query["state"][0]


def _mock_user_center_success(monkeypatch: pytest.MonkeyPatch):
    def _exchange_code_for_token(self, code: str):
        assert code
        return {"access_token": "access-token-123"}

    def _get_user_details(self, access_token: str):
        assert access_token == "access-token-123"
        return UserDetails(
            open_id="open-id-001",
            display_name="Auth Test User",
            email="auth.user@example.com",
            avatar_url="https://example.com/avatar.png",
        )

    monkeypatch.setattr(
        "backend.auth.user_center.UserCenterClient.exchange_code_for_token",
        _exchange_code_for_token,
    )
    monkeypatch.setattr(
        "backend.auth.user_center.UserCenterClient.get_user_details",
        _get_user_details,
    )


def _perform_login_callback(client: TestClient, monkeypatch: pytest.MonkeyPatch, next_path: str = "/"):
    _mock_user_center_success(monkeypatch)

    login_response = client.get("/api/auth/login", params={"next": next_path}, follow_redirects=False)
    assert login_response.status_code == 302
    state = _extract_state(login_response.headers["location"])

    callback_response = client.get(
        "/api/auth/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )
    return callback_response


def test_login_redirects_to_oauth_authorize_url_with_state(client: TestClient):
    response = client.get("/api/auth/login", params={"next": "/tasks/42"}, follow_redirects=False)

    assert response.status_code == 302
    location = response.headers["location"]
    parsed = urlparse(location)
    params = parse_qs(parsed.query)

    assert location.startswith("https://user-center.example.com/oauth/authorize")
    assert params["client_id"] == ["crawler-client"]
    assert params["redirect_uri"] == ["http://testserver/api/auth/callback"]
    assert params["response_type"] == ["code"]
    assert params["scope"] == ["basic"]
    assert "state" in params and params["state"][0]


def test_callback_with_valid_state_sets_cookie_and_redirects(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    response = _perform_login_callback(client, monkeypatch, next_path="/tasks/99")

    assert response.status_code == 302
    assert response.headers["location"] == "/tasks/99"

    set_cookie = response.headers.get("set-cookie", "")
    assert "session_token=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/" in set_cookie
    assert "Secure" not in set_cookie

    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS count FROM users")
        user_count = cur.fetchone()["count"]
        cur.execute("SELECT COUNT(*) AS count FROM sessions")
        session_count = cur.fetchone()["count"]

    assert user_count == 1
    assert session_count == 1


def test_login_sanitizes_external_next_and_callback_redirects_to_root(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _mock_user_center_success(monkeypatch)

    login_response = client.get(
        "/api/auth/login",
        params={"next": "//evil.example.com/steal"},
        follow_redirects=False,
    )
    assert login_response.status_code == 302
    state = _extract_state(login_response.headers["location"])

    callback_response = client.get(
        "/api/auth/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )
    assert callback_response.status_code == 302
    assert callback_response.headers["location"] == "/"


def test_callback_rejects_invalid_or_missing_state_and_does_not_create_session(client: TestClient):
    invalid_state_response = client.get(
        "/api/auth/callback",
        params={"code": "any-code", "state": "invalid-state"},
        follow_redirects=False,
    )
    assert invalid_state_response.status_code == 400
    assert "set-cookie" not in invalid_state_response.headers

    missing_state_response = client.get(
        "/api/auth/callback",
        params={"code": "any-code"},
        follow_redirects=False,
    )
    assert missing_state_response.status_code == 400
    assert "set-cookie" not in missing_state_response.headers

    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS count FROM sessions")
        session_count = cur.fetchone()["count"]
    assert session_count == 0


def test_callback_rejects_state_without_matching_oauth_nonce_cookie(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _mock_user_center_success(monkeypatch)

    login_response = client.get("/api/auth/login", follow_redirects=False)
    assert login_response.status_code == 302
    state = _extract_state(login_response.headers["location"])

    with TestClient(app) as other_client:
        response = other_client.get(
            "/api/auth/callback",
            params={"code": "valid-code", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 400
    assert "set-cookie" not in response.headers
    payload = response.json()
    assert payload["error_code"] == "invalid_oauth_state"

    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS count FROM sessions")
        session_count = cur.fetchone()["count"]
    assert session_count == 0


def test_callback_user_center_unavailable_returns_502_without_session(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    login_response = client.get("/api/auth/login", follow_redirects=False)
    state = _extract_state(login_response.headers["location"])

    def _exchange_code_for_token(_self, _code: str):
        raise UserCenterServerError(status_code=502, detail="登录服务暂不可用，请稍后重试")

    monkeypatch.setattr(
        "backend.auth.user_center.UserCenterClient.exchange_code_for_token",
        _exchange_code_for_token,
    )

    response = client.get(
        "/api/auth/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 502
    payload = response.json()
    assert payload["success"] is False
    assert "登录服务暂不可用" in payload["error"]

    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS count FROM sessions")
        session_count = cur.fetchone()["count"]
    assert session_count == 0


def test_me_returns_200_with_user_when_authenticated(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    callback_response = _perform_login_callback(client, monkeypatch)
    assert callback_response.status_code == 302

    response = client.get("/api/auth/me")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    user = payload["data"]["user"]
    assert user["display_name"] == "Auth Test User"
    assert user["external_id"] == "open-id-001"
    assert user["openId"] == "open-id-001"


def test_me_returns_401_when_no_valid_cookie(client: TestClient):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    payload = response.json()
    assert payload["success"] is False


def test_logout_deletes_session_clears_cookie_and_returns_logout_url_config(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    callback_response = _perform_login_callback(client, monkeypatch)
    assert callback_response.status_code == 302

    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS count FROM sessions")
        assert cur.fetchone()["count"] == 1

    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "logoutUriConfig" in payload["data"]
    assert "default" in payload["data"]["logoutUriConfig"]
    assert payload["data"]["logoutUriConfig"]["default"].startswith("https://user-center.example.com")

    set_cookie = response.headers.get("set-cookie", "")
    assert "session_token=" in set_cookie
    assert "Max-Age=0" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/" in set_cookie

    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS count FROM sessions")
        assert cur.fetchone()["count"] == 0


def test_callback_sets_secure_cookie_in_production(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENV", "production")
    with TestClient(app, base_url="https://testserver") as secure_client:
        response = _perform_login_callback(secure_client, monkeypatch)
        assert response.status_code == 302
        set_cookie = response.headers.get("set-cookie", "")
        assert "Secure" in set_cookie

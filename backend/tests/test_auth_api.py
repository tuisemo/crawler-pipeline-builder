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
    assert params["redirect_uri"][0] == "http://testserver/api/auth/callback"
    # No cookie is set — OAuth state CSRF protection relies on Redis only
    assert "crawler_workflow_oauth_state=" not in response.headers.get("set-cookie", "")
    payload = consume_oauth_state(params["state"][0])
    assert payload is not None
    assert payload["code_verifier"]


def test_callback_with_valid_state_redirects_to_frontend(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    response, _ = _perform_login_callback(client, monkeypatch)

    assert response.status_code == 302
    location = response.headers["location"]
    assert "sessionId=" in location
    assert "nextPath=" in location
    assert location.startswith("/#/auth/callback")

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


def test_callback_redirect_uses_relative_frontend_path_when_frontend_url_missing(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("USER_CENTER_FRONTEND_URL", raising=False)
    monkeypatch.setattr("core.settings.load_env_config", lambda *args, **kwargs: {})
    response, _ = _perform_login_callback(client, monkeypatch)
    assert response.status_code == 302
    assert response.headers["location"].startswith("/#/auth/callback")


def test_callback_redirect_ignores_redirect_uri_origin_and_uses_relative_frontend_path(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("USER_CENTER_FRONTEND_URL", raising=False)
    monkeypatch.setenv("USER_CENTER_REDIRECT_URI", "https://app.example.com/auth/callback")
    monkeypatch.setattr("core.settings.load_env_config", lambda *args, **kwargs: {})
    response, _ = _perform_login_callback(client, monkeypatch)
    assert response.status_code == 302
    assert response.headers["location"].startswith("/#/auth/callback")


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


def test_callback_uses_redirect_uri_captured_at_login(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    login_response = client.get("/api/auth/login", params={"next": "/dashboard"}, follow_redirects=False)
    state = _extract_state(login_response.headers["location"])

    # Simulate runtime config drift between login and callback
    monkeypatch.setenv("USER_CENTER_REDIRECT_URI", "https://wrong.example.com/api/auth/callback")

    async def _exchange_code_for_token(*, code: str, redirect_uri: str, code_verifier: str | None = None):
        assert redirect_uri == "http://testserver/api/auth/callback"
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

    callback_response = client.get(
        "/api/auth/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )
    assert callback_response.status_code == 302


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
    assert "sessionId=" in callback_response.headers["location"]

    # Original client can no longer use the same state once any client consumed it.
    valid_response = client.get(
        "/api/auth/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )
    assert valid_response.status_code == 302
    assert "error=invalid_oauth_state" in valid_response.headers["location"]


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


# ── Frontend-driven OAuth flow tests ──────────────────────


def _mock_async_user_center_success(monkeypatch: pytest.MonkeyPatch):
    """Mock helpers for the new frontend-driven authorize + token flow."""

    async def _exchange_code_for_token(*, code: str, redirect_uri: str, code_verifier: str | None = None):
        assert code
        assert redirect_uri
        return {
            "access_token": "access-token-002",
            "refresh_token": "refresh-token-002",
            "expires_in": 3600,
            "name": "Token Test User",
        }

    monkeypatch.setattr("api.auth_routes.exchange_code_for_token", _exchange_code_for_token)
    monkeypatch.setattr(
        "api.auth_routes.derive_local_user_profile_from_token",
        lambda token: {
            "external_id": "open-id-002",
            "display_name": token.get("name") or "Token Test User",
            "email": "token.user@example.com",
            "avatar_url": "https://example.com/token-avatar.png",
        },
    )


def _perform_authorize_token(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """Helper: complete the new authorize → token flow end-to-end."""
    _mock_async_user_center_success(monkeypatch)

    # Step 1: POST /api/auth/authorize
    authorize_response = client.post(
        "/api/auth/authorize",
        json={"next_path": "/dashboard", "redirect_uri": "http://testserver/"},
    )
    assert authorize_response.status_code == 200
    authorize_data = authorize_response.json()
    assert authorize_data["success"] is True
    authorize_url = authorize_data["data"]["authorize_url"]
    state = authorize_data["data"]["state"]
    assert authorize_url.startswith("https://user-center.example.com/oauth/authorize")
    assert state

    # Step 2: POST /api/auth/token
    token_response = client.post(
        "/api/auth/token",
        json={"code": "valid-code-002", "state": state},
    )
    return token_response, state


class TestAuthorizeEndpoint:
    def test_authorize_returns_authorize_url_and_state(self, client: TestClient):
        response = client.post(
            "/api/auth/authorize",
            json={"next_path": "/tasks", "redirect_uri": "http://testserver/"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "authorize_url" in data["data"]
        assert "state" in data["data"]
        assert data["data"]["authorize_url"].startswith("https://user-center.example.com/oauth/authorize")

    def test_authorize_uses_frontend_declared_redirect_uri(self, client: TestClient):
        response = client.post(
            "/api/auth/authorize",
            json={"next_path": "/tasks", "redirect_uri": "http://testserver/"},
        )
        data = response.json()
        authorize_url = data["data"]["authorize_url"]
        parsed = urlparse(authorize_url)
        params = parse_qs(parsed.query)
        assert params["redirect_uri"][0] == "http://testserver/"

    def test_authorize_uses_config_redirect_uri_when_no_frontend_uri(self, client: TestClient):
        response = client.post(
            "/api/auth/authorize",
            json={"next_path": "/tasks"},
        )
        data = response.json()
        authorize_url = data["data"]["authorize_url"]
        parsed = urlparse(authorize_url)
        params = parse_qs(parsed.query)
        assert params["redirect_uri"][0] == "http://testserver/"

    def test_authorize_validates_redirect_uri_scheme(self, client: TestClient):
        response = client.post(
            "/api/auth/authorize",
            json={"next_path": "/tasks", "redirect_uri": "ftp://evil.com/"},
        )
        assert response.status_code == 400

    def test_authorize_rejects_redirect_uri_with_query(self, client: TestClient):
        response = client.post(
            "/api/auth/authorize",
            json={"next_path": "/tasks", "redirect_uri": "http://testserver/?foo=bar"},
        )
        assert response.status_code == 400

    def test_authorize_rejects_redirect_uri_with_fragment(self, client: TestClient):
        response = client.post(
            "/api/auth/authorize",
            json={"next_path": "/tasks", "redirect_uri": "http://testserver/#/callback"},
        )
        assert response.status_code == 400

    def test_authorize_allows_localhost_redirect_uri(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("USER_CENTER_FRONTEND_URL", "http://127.0.0.1:3101")
        response = client.post(
            "/api/auth/authorize",
            json={"next_path": "/tasks", "redirect_uri": "http://127.0.0.1:3101/"},
        )
        assert response.status_code == 200

    def test_authorize_rejects_non_matching_host_in_production(self, client: TestClient):
        """Non-localhost redirect_uri mismatch is rejected in production."""
        response = client.post(
            "/api/auth/authorize",
            json={"next_path": "/tasks", "redirect_uri": "https://evil.com/"},
        )
        assert response.status_code == 400

    def test_authorize_allows_configured_frontend_url_behind_reverse_proxy(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("USER_CENTER_FRONTEND_URL", "https://test.zhongshu.tech/crawler-studio")
        response = client.post(
            "/api/auth/authorize",
            json={"next_path": "/tasks", "redirect_uri": "https://test.zhongshu.tech/crawler-studio/"},
            headers={
                "host": "127.0.0.1:8000",
            },
        )
        assert response.status_code == 200

    def test_authorize_sanitizes_next_path(self, client: TestClient):
        response = client.post(
            "/api/auth/authorize",
            json={"next_path": "https://evil.com/steal", "redirect_uri": "http://testserver/"},
        )
        assert response.status_code == 200
        state = response.json()["data"]["state"]
        from auth.session import consume_oauth_state
        payload = consume_oauth_state(state)
        assert payload["next_path"] == "/"


class TestTokenEndpoint:
    def test_token_exchange_returns_session_and_user(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        response, _ = _perform_authorize_token(client, monkeypatch)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "session_id" in data["data"]
        assert data["data"]["user"]["display_name"] == "Token Test User"
        assert data["data"]["user"]["external_id"] == "open-id-002"
        assert data["data"]["auth"]["session_status"] == "active"
        assert data["data"]["auth"]["has_refresh_token"] is True
        assert data["data"]["next_path"] == "/dashboard"

    def test_token_session_is_valid_for_me(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        response, _ = _perform_authorize_token(client, monkeypatch)
        session_id = response.json()["data"]["session_id"]

        me_response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {session_id}"})
        assert me_response.status_code == 200
        me_data = me_response.json()
        assert me_data["data"]["user"]["display_name"] == "Token Test User"

    def test_token_rejects_invalid_state(self, client: TestClient):
        response = client.post(
            "/api/auth/token",
            json={"code": "valid-code", "state": "non-existent-state"},
        )
        assert response.status_code == 400

    def test_token_consumes_state_once(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        response, state = _perform_authorize_token(client, monkeypatch)
        assert response.status_code == 200

        # Second attempt with same state should fail
        second_response = client.post(
            "/api/auth/token",
            json={"code": "valid-code-002", "state": state},
        )
        assert second_response.status_code == 400

    def test_token_creates_user_in_database(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        _perform_authorize_token(client, monkeypatch)
        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS count FROM users")
            assert cur.fetchone()["count"] == 1

    def test_token_uses_redirect_uri_from_state(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """Token exchange uses the redirect_uri stored in Redis state, not re-derived."""
        _mock_async_user_center_success(monkeypatch)

        # Authorize with explicit redirect_uri
        authorize_response = client.post(
            "/api/auth/authorize",
            json={"next_path": "/", "redirect_uri": "http://testserver/"},
        )
        state = authorize_response.json()["data"]["state"]

        # Simulate config drift — env redirect_uri changes after authorize
        monkeypatch.setenv("USER_CENTER_REDIRECT_URI", "https://wrong.example.com/api/auth/callback")

        # Verify exchange still uses the original redirect_uri from state
        async def _assert_original_redirect_uri(*, code, redirect_uri, code_verifier=None):
            assert redirect_uri == "http://testserver/"
            return {
                "access_token": "access-token-002",
                "refresh_token": "refresh-token-002",
                "expires_in": 3600,
                "name": "Token Test User",
            }

        monkeypatch.setattr("api.auth_routes.exchange_code_for_token", _assert_original_redirect_uri)
        monkeypatch.setattr(
            "api.auth_routes.derive_local_user_profile_from_token",
            lambda token: {
                "external_id": "open-id-002",
                "display_name": "Token Test User",
                "email": "token.user@example.com",
                "avatar_url": None,
            },
        )

        token_response = client.post(
            "/api/auth/token",
            json={"code": "valid-code-002", "state": state},
        )
        assert token_response.status_code == 200

    def test_token_skips_user_info_call_when_token_claims_are_sufficient(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        _mock_async_user_center_success(monkeypatch)

        async def _unexpected_fetch_user_info(*_args, **_kwargs):
            raise AssertionError("fetch_user_info should not be called when token claims already contain openId")

        monkeypatch.setattr("api.auth_routes.fetch_user_info", _unexpected_fetch_user_info)

        response, _ = _perform_authorize_token(client, monkeypatch)
        assert response.status_code == 200

    def test_token_falls_back_to_user_info_when_token_claims_missing_openid(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        async def _exchange(*, code, redirect_uri, code_verifier=None):
            return {
                "access_token": "at",
                "refresh_token": "rt",
                "expires_in": 3600,
            }

        async def _fetch_user_info(_access_token: str):
            return {
                "openId": "open-id-api-123",
                "personName": "Profile User",
                "email": "profile.user@example.com",
                "imageUrl": "https://example.com/profile-avatar.png",
            }

        monkeypatch.setattr("api.auth_routes.exchange_code_for_token", _exchange)
        monkeypatch.setattr(
            "api.auth_routes.derive_local_user_profile_from_token",
            lambda token: {"external_id": None, "display_name": "OAuth User", "email": None, "avatar_url": None},
        )
        monkeypatch.setattr("api.auth_routes.fetch_user_info", _fetch_user_info)

        auth_resp = client.post("/api/auth/authorize", json={"next_path": "/", "redirect_uri": "http://testserver/"})
        state = auth_resp.json()["data"]["state"]

        token_resp = client.post("/api/auth/token", json={"code": "c", "state": state})
        assert token_resp.status_code == 200
        payload = token_resp.json()["data"]["user"]
        assert payload["external_id"] == "open-id-api-123"
        assert payload["display_name"] == "Profile User"

    def test_token_rejects_missing_openid(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """Token exchange fails when user center returns no openId."""
        monkeypatch.setattr(
            "api.auth_routes.exchange_code_for_token",
            _mock_async_user_center_success(monkeypatch).__wrapped__
            if hasattr(_mock_async_user_center_success, "__wrapped__")
            else lambda **kw: {"access_token": "at", "expires_in": 3600},
        )

        async def _exchange(*, code, redirect_uri, code_verifier=None):
            return {"access_token": "at", "expires_in": 3600}

        monkeypatch.setattr("api.auth_routes.exchange_code_for_token", _exchange)
        monkeypatch.setattr(
            "api.auth_routes.derive_local_user_profile_from_token",
            lambda token: {"external_id": None, "display_name": "X", "email": None, "avatar_url": None},
        )

        async def _fetch_user_info(_access_token: str):
            return {"displayName": "X"}

        monkeypatch.setattr("api.auth_routes.fetch_user_info", _fetch_user_info)

        # Authorize first
        auth_resp = client.post("/api/auth/authorize", json={"next_path": "/", "redirect_uri": "http://testserver/"})
        state = auth_resp.json()["data"]["state"]

        token_resp = client.post("/api/auth/token", json={"code": "c", "state": state})
        assert token_resp.status_code == 400


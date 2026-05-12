"""Tests for the user center HTTP client.

Covers:
- build_authorize_url constructs standard OAuth2 authorize URL
- exchange_code_for_token POSTs to /oauth/token and returns access_token response
- get_user_details POSTs to /user/get with access_token and returns UserDetails
- Network errors raise UserCenterNetworkError
- Timeouts raise UserCenterTimeoutError
- 5xx responses raise UserCenterServerError with user-friendly message
- All calls have reasonable timeout (10s)
- state parameter is cryptographically random
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.auth.user_center import (
    UserCenterClient,
    UserCenterNetworkError,
    UserCenterServerError,
    UserCenterTimeoutError,
    UserDetails,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

def _make_settings(**overrides):
    """Create a minimal CrawlerWorkflowSettings-like object for tests."""
    defaults = dict(
        user_center_base_uri="https://uc.example.com",
        user_center_client_id="test-client-id",
        user_center_client_secret="test-client-secret",
        user_center_scope="basic",
        user_center_redirect_uri="https://app.example.com/api/auth/callback",
    )
    defaults.update(overrides)
    return MagicMock(**defaults)


@pytest.fixture
def settings():
    return _make_settings()


@pytest.fixture
def client(settings):
    return UserCenterClient(settings)


# ── build_authorize_url ──────────────────────────────────────────────────


class TestBuildAuthorizeUrl:
    def test_constructs_standard_oauth2_authorize_url(self, client):
        url = client.build_authorize_url(state="random-state", redirect_uri="https://app.example.com/api/auth/callback")
        assert url.startswith("https://uc.example.com/oauth/authorize?")
        assert "client_id=test-client-id" in url
        assert "redirect_uri=" in url
        assert "response_type=code" in url
        assert "scope=basic" in url
        assert "state=random-state" in url

    def test_url_contains_all_required_oauth2_params(self, client):
        from urllib.parse import parse_qs, urlparse

        url = client.build_authorize_url(state="abc123", redirect_uri="https://app.example.com/api/auth/callback")
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert params["client_id"] == ["test-client-id"]
        assert params["redirect_uri"] == ["https://app.example.com/api/auth/callback"]
        assert params["response_type"] == ["code"]
        assert params["scope"] == ["basic"]
        assert params["state"] == ["abc123"]

    def test_uses_redirect_uri_argument_over_settings(self, client):
        from urllib.parse import parse_qs, urlparse

        custom_redirect = "https://custom.example.com/callback"
        url = client.build_authorize_url(state="xyz", redirect_uri=custom_redirect)
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert params["redirect_uri"] == [custom_redirect]

    def test_uses_settings_redirect_uri_when_not_provided(self, client):
        from urllib.parse import parse_qs, urlparse

        url = client.build_authorize_url(state="xyz")
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert params["redirect_uri"] == ["https://app.example.com/api/auth/callback"]


# ── generate_state ──────────────────────────────────────────────────────


class TestGenerateState:
    def test_state_is_cryptographically_random(self, client):
        state1 = client.generate_state()
        state2 = client.generate_state()
        assert state1 != state2

    def test_state_has_sufficient_length(self, client):
        state = client.generate_state()
        # At least 32 bytes = 64 hex chars, or at least 43 base64url chars
        assert len(state) >= 32

    def test_state_is_url_safe(self, client):
        import re
        state = client.generate_state()
        # URL-safe base64 or hex characters only
        assert re.match(r'^[A-Za-z0-9_-]+$', state) or re.match(r'^[a-f0-9]+$', state)


# ── exchange_code_for_token ──────────────────────────────────────────────


class TestExchangeCodeForToken:
    @patch("backend.auth.user_center.requests.post")
    def test_posts_to_oauth_token_endpoint(self, mock_post, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "at-123", "token_type": "Bearer", "expires_in": 3600}
        mock_post.return_value = mock_response

        result = client.exchange_code_for_token(code="auth-code-123")

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://uc.example.com/oauth/token"
        assert call_args[1]["data"]["code"] == "auth-code-123"
        assert call_args[1]["data"]["client_id"] == "test-client-id"
        assert call_args[1]["data"]["client_secret"] == "test-client-secret"
        assert call_args[1]["data"]["grant_type"] == "authorization_code"
        assert call_args[1]["data"]["redirect_uri"] == "https://app.example.com/api/auth/callback"

    @patch("backend.auth.user_center.requests.post")
    def test_returns_access_token_on_success(self, mock_post, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "at-123", "token_type": "Bearer", "expires_in": 3600}
        mock_post.return_value = mock_response

        result = client.exchange_code_for_token(code="auth-code-123")
        assert result["access_token"] == "at-123"

    @patch("backend.auth.user_center.requests.post")
    def test_has_reasonable_timeout(self, mock_post, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "at-123"}
        mock_post.return_value = mock_response

        client.exchange_code_for_token(code="code")

        call_args = mock_post.call_args
        assert call_args[1]["timeout"] <= 15
        assert call_args[1]["timeout"] >= 5

    @patch("backend.auth.user_center.requests.post")
    def test_raises_server_error_on_5xx(self, mock_post, client):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        with pytest.raises(UserCenterServerError) as exc_info:
            client.exchange_code_for_token(code="code")
        # Should have user-friendly message, not raw server output
        assert "登录服务暂不可用" in str(exc_info.value) or "unavailable" in str(exc_info.value).lower()

    @patch("backend.auth.user_center.requests.post")
    def test_raises_server_error_on_502(self, mock_post, client):
        mock_response = MagicMock()
        mock_response.status_code = 502
        mock_response.text = "Bad Gateway"
        mock_post.return_value = mock_response

        with pytest.raises(UserCenterServerError):
            client.exchange_code_for_token(code="code")

    @patch("backend.auth.user_center.requests.post")
    def test_raises_timeout_error_on_timeout(self, mock_post, client):
        import requests as req
        mock_post.side_effect = req.exceptions.Timeout("Connection timed out")

        with pytest.raises(UserCenterTimeoutError):
            client.exchange_code_for_token(code="code")

    @patch("backend.auth.user_center.requests.post")
    def test_raises_network_error_on_connection_error(self, mock_post, client):
        import requests as req
        mock_post.side_effect = req.exceptions.ConnectionError("Connection refused")

        with pytest.raises(UserCenterNetworkError):
            client.exchange_code_for_token(code="code")

    @patch("backend.auth.user_center.requests.post")
    def test_raises_network_error_on_generic_request_exception(self, mock_post, client):
        import requests as req
        mock_post.side_effect = req.exceptions.RequestException("Something went wrong")

        with pytest.raises(UserCenterNetworkError):
            client.exchange_code_for_token(code="code")

    @patch("backend.auth.user_center.requests.post")
    def test_raises_server_error_on_503(self, mock_post, client):
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.text = "Service Unavailable"
        mock_post.return_value = mock_response

        with pytest.raises(UserCenterServerError):
            client.exchange_code_for_token(code="code")

    @patch("backend.auth.user_center.requests.post")
    def test_server_error_does_not_expose_internal_details(self, mock_post, client):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "java.lang.NullPointerException at com.internal.AuthService"
        mock_post.return_value = mock_response

        with pytest.raises(UserCenterServerError) as exc_info:
            client.exchange_code_for_token(code="code")
        error_msg = str(exc_info.value)
        # Should NOT contain internal stack trace info
        assert "java.lang" not in error_msg
        assert "NullPointerException" not in error_msg


# ── get_user_details ──────────────────────────────────────────────────────


class TestGetUserDetails:
    @patch("backend.auth.user_center.requests.post")
    def test_posts_to_user_get_endpoint(self, mock_post, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "openId": "user-open-id-123",
            "displayName": "Test User",
            "email": "test@example.com",
            "avatarUrl": "https://avatar.example.com/test.png",
        }
        mock_post.return_value = mock_response

        result = client.get_user_details(access_token="at-123")

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://uc.example.com/user/get"

    @patch("backend.auth.user_center.requests.post")
    def test_sends_access_token_in_body(self, mock_post, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "openId": "user-open-id-123",
            "displayName": "Test User",
        }
        mock_post.return_value = mock_response

        client.get_user_details(access_token="at-123")

        call_args = mock_post.call_args
        assert call_args[1]["json"]["access_token"] == "at-123"

    @patch("backend.auth.user_center.requests.post")
    def test_returns_user_details_on_success(self, mock_post, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "openId": "user-open-id-123",
            "displayName": "Test User",
            "email": "test@example.com",
            "avatarUrl": "https://avatar.example.com/test.png",
        }
        mock_post.return_value = mock_response

        result = client.get_user_details(access_token="at-123")
        assert isinstance(result, UserDetails)
        assert result.open_id == "user-open-id-123"
        assert result.display_name == "Test User"
        assert result.email == "test@example.com"
        assert result.avatar_url == "https://avatar.example.com/test.png"

    @patch("backend.auth.user_center.requests.post")
    def test_handles_missing_optional_fields(self, mock_post, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "openId": "user-open-id-123",
            "displayName": "Test User",
        }
        mock_post.return_value = mock_response

        result = client.get_user_details(access_token="at-123")
        assert result.open_id == "user-open-id-123"
        assert result.display_name == "Test User"
        assert result.email is None
        assert result.avatar_url is None

    @patch("backend.auth.user_center.requests.post")
    def test_has_reasonable_timeout(self, mock_post, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "openId": "id",
            "displayName": "User",
        }
        mock_post.return_value = mock_response

        client.get_user_details(access_token="at-123")

        call_args = mock_post.call_args
        assert call_args[1]["timeout"] <= 15
        assert call_args[1]["timeout"] >= 5

    @patch("backend.auth.user_center.requests.post")
    def test_raises_server_error_on_5xx(self, mock_post, client):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        with pytest.raises(UserCenterServerError):
            client.get_user_details(access_token="at-123")

    @patch("backend.auth.user_center.requests.post")
    def test_raises_timeout_error_on_timeout(self, mock_post, client):
        import requests as req
        mock_post.side_effect = req.exceptions.Timeout("Connection timed out")

        with pytest.raises(UserCenterTimeoutError):
            client.get_user_details(access_token="at-123")

    @patch("backend.auth.user_center.requests.post")
    def test_raises_network_error_on_connection_error(self, mock_post, client):
        import requests as req
        mock_post.side_effect = req.exceptions.ConnectionError("Connection refused")

        with pytest.raises(UserCenterNetworkError):
            client.get_user_details(access_token="at-123")

    @patch("backend.auth.user_center.requests.post")
    def test_server_error_does_not_expose_internal_details(self, mock_post, client):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "java.lang.NullPointerException at com.internal.UserService"
        mock_post.return_value = mock_response

        with pytest.raises(UserCenterServerError) as exc_info:
            client.get_user_details(access_token="at-123")
        error_msg = str(exc_info.value)
        assert "java.lang" not in error_msg
        assert "NullPointerException" not in error_msg


# ── Exception hierarchy ───────────────────────────────────────────────────


class TestExceptionHierarchy:
    def test_timeout_error_is_not_generic_exception(self):
        assert UserCenterTimeoutError.__bases__[0].__name__ != "Exception"

    def test_network_error_is_not_generic_exception(self):
        assert UserCenterNetworkError.__bases__[0].__name__ != "Exception"

    def test_server_error_is_not_generic_exception(self):
        assert UserCenterServerError.__bases__[0].__name__ != "Exception"

    def test_all_errors_inherit_from_common_base(self):
        from backend.auth.user_center import UserCenterError
        assert issubclass(UserCenterTimeoutError, UserCenterError)
        assert issubclass(UserCenterNetworkError, UserCenterError)
        assert issubclass(UserCenterServerError, UserCenterError)

    def test_server_error_stores_status_code(self):
        err = UserCenterServerError(500, "Internal Server Error")
        assert err.status_code == 500


# ── Integration-style: full flow with mocked HTTP ────────────────────────


class TestFullFlow:
    @patch("backend.auth.user_center.requests.post")
    def test_authorize_url_to_token_to_user_details(self, mock_post, client):
        # Step 1: build authorize URL
        url = client.build_authorize_url(state="test-state", redirect_uri="https://app.example.com/api/auth/callback")
        assert "oauth/authorize" in url
        assert "state=test-state" in url

        # Step 2: exchange code for token
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {"access_token": "at-xyz", "token_type": "Bearer"}

        # Step 3: get user details
        user_response = MagicMock()
        user_response.status_code = 200
        user_response.json.return_value = {
            "openId": "open-id-xyz",
            "displayName": "Flow User",
            "email": "flow@example.com",
        }

        mock_post.side_effect = [token_response, user_response]

        token_result = client.exchange_code_for_token(code="code-xyz")
        assert token_result["access_token"] == "at-xyz"

        user_result = client.get_user_details(access_token="at-xyz")
        assert user_result.open_id == "open-id-xyz"
        assert user_result.display_name == "Flow User"

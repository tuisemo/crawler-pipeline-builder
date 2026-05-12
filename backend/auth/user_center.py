"""HTTP client for user center OAuth2 integration.

Provides:
- build_authorize_url: constructs standard OAuth2 authorize URL
- exchange_code_for_token: exchanges authorization code for access token
- get_user_details: fetches user details using access token
- generate_state: generates cryptographically random state parameter

Error handling:
- UserCenterTimeoutError: request timeout
- UserCenterNetworkError: connection / generic network failure
- UserCenterServerError: user center returned 5xx response
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import requests


# ── Exceptions ────────────────────────────────────────────────────────────


class UserCenterError(Exception):
    """Base exception for all user-center errors."""


class UserCenterTimeoutError(UserCenterError):
    """Raised when a request to the user center times out."""


class UserCenterNetworkError(UserCenterError):
    """Raised when a network-level error occurs contacting the user center."""


class UserCenterServerError(UserCenterError):
    """Raised when the user center returns a 5xx response."""

    def __init__(self, status_code: int, detail: str = "") -> None:
        self.status_code = status_code
        super().__init__(detail)


# ── Data models ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UserDetails:
    """User information returned by the user center /user/get endpoint."""

    open_id: str
    display_name: str
    email: str | None = None
    avatar_url: str | None = None


# ── Client ────────────────────────────────────────────────────────────────

_DEFAULT_TIMEOUT_SECONDS = 10


class UserCenterClient:
    """HTTP client for user center OAuth2 integration.

    The BFF constructs the OAuth2 authorize URL directly (no call to the
    user center needed). Token exchange and user-info retrieval are POST
    requests with proper error handling and timeouts.
    """

    def __init__(self, settings) -> None:
        self._base_uri = settings.user_center_base_uri.rstrip("/")
        self._client_id = settings.user_center_client_id
        self._client_secret = settings.user_center_client_secret
        self._scope = settings.user_center_scope
        self._redirect_uri = settings.user_center_redirect_uri
        self._timeout = _DEFAULT_TIMEOUT_SECONDS

    # ── Public API ────────────────────────────────────────────────────────

    def build_authorize_url(self, state: str, redirect_uri: str | None = None) -> str:
        """Construct the standard OAuth2 authorize URL.

        The BFF builds this URL directly — no HTTP call to the user center
        is needed for this step.

        Args:
            state: Cryptographically random string for CSRF protection.
            redirect_uri: Override for the callback URL. Falls back to the
                          value from settings if not provided.

        Returns:
            Fully-qualified OAuth2 authorize URL.
        """
        resolved_redirect = redirect_uri or self._redirect_uri
        params = {
            "client_id": self._client_id,
            "redirect_uri": resolved_redirect,
            "response_type": "code",
            "scope": self._scope,
            "state": state,
        }
        return f"{self._base_uri}/oauth/authorize?{urlencode(params)}"

    @staticmethod
    def generate_state() -> str:
        """Generate a cryptographically random state parameter.

        Uses ``secrets.token_urlsafe`` which produces a URL-safe base64
        string with at least 32 bytes of entropy.
        """
        return secrets.token_urlsafe(32)

    def exchange_code_for_token(self, code: str) -> dict:
        """Exchange an authorization code for an access token.

        POSTs to ``{base_uri}/oauth/token`` with the code, client
        credentials, and grant type.

        Args:
            code: Authorization code received from the user center callback.

        Returns:
            Parsed JSON response containing at least ``access_token``.

        Raises:
            UserCenterTimeoutError: Request timed out.
            UserCenterNetworkError: Network-level failure.
            UserCenterServerError: User center returned 5xx.
        """
        url = f"{self._base_uri}/oauth/token"
        data = {
            "code": code,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "authorization_code",
            "redirect_uri": self._redirect_uri,
        }
        return self._post_form(url, data)

    def get_user_details(self, access_token: str) -> UserDetails:
        """Fetch user details from the user center.

        POSTs to ``{base_uri}/user/get`` with the access token.

        Args:
            access_token: Token obtained from ``exchange_code_for_token``.

        Returns:
            UserDetails with open_id, display_name, and optional fields.

        Raises:
            UserCenterTimeoutError: Request timed out.
            UserCenterNetworkError: Network-level failure.
            UserCenterServerError: User center returned 5xx.
        """
        url = f"{self._base_uri}/user/get"
        payload = {"access_token": access_token}
        raw = self._post_json(url, payload)
        return UserDetails(
            open_id=raw.get("openId", ""),
            display_name=raw.get("displayName", ""),
            email=raw.get("email"),
            avatar_url=raw.get("avatarUrl"),
        )

    # ── Internal helpers ──────────────────────────────────────────────────

    def _post_form(self, url: str, data: dict) -> dict:
        """POST with form-encoded data, with error handling."""
        try:
            resp = requests.post(url, data=data, timeout=self._timeout)
        except requests.exceptions.Timeout as exc:
            raise UserCenterTimeoutError(str(exc)) from exc
        except requests.exceptions.ConnectionError as exc:
            raise UserCenterNetworkError(str(exc)) from exc
        except requests.exceptions.RequestException as exc:
            raise UserCenterNetworkError(str(exc)) from exc

        self._check_status(resp)
        return resp.json()

    def _post_json(self, url: str, payload: dict) -> dict:
        """POST with JSON body, with error handling."""
        try:
            resp = requests.post(url, json=payload, timeout=self._timeout)
        except requests.exceptions.Timeout as exc:
            raise UserCenterTimeoutError(str(exc)) from exc
        except requests.exceptions.ConnectionError as exc:
            raise UserCenterNetworkError(str(exc)) from exc
        except requests.exceptions.RequestException as exc:
            raise UserCenterNetworkError(str(exc)) from exc

        self._check_status(resp)
        return resp.json()

    @staticmethod
    def _check_status(resp: requests.Response) -> None:
        """Raise UserCenterServerError for 5xx responses.

        The error message is user-friendly and does not expose internal
        details from the upstream server.
        """
        if 500 <= resp.status_code < 600:
            raise UserCenterServerError(
                status_code=resp.status_code,
                detail="登录服务暂不可用，请稍后重试",
            )

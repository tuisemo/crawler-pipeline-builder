"""User-center OAuth and profile helpers."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from auth.oauth_config import (
    create_oauth_client,
    get_access_token_url,
    get_authorize_url,
    get_user_details_url,
)

logger = logging.getLogger(__name__)

_SAFE_TOKEN_FIELDS = {"token_type", "expires_in", "scope", "expires_at"}


class UserCenterError(Exception):
    """Raised when the user center OAuth/profile exchange fails."""

    def __init__(self, message: str, *, error_code: str = "user_center_error") -> None:
        super().__init__(message)
        self.error_code = error_code


def build_authorize_url(*, redirect_uri: str, state: str, code_verifier: str | None = None) -> str:
    """Build the user-center authorize URL using Authlib.

    Uses ``response_type=code openid`` so the token endpoint returns
    ``open_id`` alongside the access token (matches the Java SDK behaviour).
    """
    client = create_oauth_client(redirect_uri=redirect_uri)
    kwargs: dict[str, Any] = {"state": state, "response_type": "code openid"}
    if code_verifier:
        kwargs["code_verifier"] = code_verifier
    authorize_url, _ = client.create_authorization_url(get_authorize_url(), **kwargs)
    return authorize_url


async def exchange_code_for_token(
    *,
    code: str,
    redirect_uri: str,
    code_verifier: str | None = None,
) -> dict[str, Any]:
    """Exchange an authorization code for user-center tokens."""
    client = create_oauth_client(redirect_uri=redirect_uri)
    fetch_kwargs: dict[str, Any] = {
        "code": code,
        "grant_type": "authorization_code",
    }
    if code_verifier:
        fetch_kwargs["code_verifier"] = code_verifier

    try:
        token = await client.fetch_token(
            url=get_access_token_url(),
            **fetch_kwargs,
        )
    except Exception as exc:  # pragma: no cover - authlib exception surface is broad
        raise UserCenterError("Failed to exchange authorization code", error_code="oauth_exchange_failed") from exc
    finally:
        await client.aclose()

    logger.info(
        "User center /oauth/token response keys: %s",
        list(token.keys()) if isinstance(token, dict) else type(token),
    )
    if isinstance(token, dict):
        safe_fields = {k: v for k, v in token.items() if k in _SAFE_TOKEN_FIELDS}
        logger.info(
            "User center /oauth/token safe fields: %s",
            safe_fields,
        )

    access_token = token.get("access_token")
    if not access_token:
        raise UserCenterError("User center token response did not include access_token", error_code="oauth_invalid_token")
    return token


async def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    """Refresh OAuth2 access token using the standard token endpoint."""
    client = create_oauth_client()
    try:
        token = await client.refresh_token(
            url=get_access_token_url(),
            refresh_token=refresh_token,
        )
    except Exception as exc:  # pragma: no cover
        raise UserCenterError("Failed to refresh access token", error_code="oauth_refresh_failed") from exc
    finally:
        await client.aclose()

    access_token = token.get("access_token")
    if not access_token:
        raise UserCenterError(
            "User center refresh response did not include access_token",
            error_code="oauth_invalid_token",
        )
    return token


async def fetch_user_info(access_token: str) -> dict[str, Any]:
    """Fetch user information from the user center server.

    Calls the user center's /server/public/user/get endpoint with
    Bearer token (matching the Java SDK's UserCenterPublicApi).
    """
    from core.settings import get_settings

    settings = get_settings()
    profile_url = f"{settings.user_center_base_uri.rstrip('/')}/server/public/user/get"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                profile_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise UserCenterError(
            "Failed to fetch user details from user center",
            error_code="user_center_profile_failed",
        ) from exc

    if not isinstance(payload, dict):
        raise UserCenterError(
            "User center /server/public/user/get response is not a valid object",
            error_code="user_center_profile_failed",
        )
    logger.info("User center /server/public/user/get response keys=%s", list(payload.keys()))

    if payload.get("respCode") and payload.get("respCode") != "SUCCESS":
        raise UserCenterError(
            f"User center /server/public/user/get error: {payload.get('respMsg', 'unknown')}",
            error_code="user_center_profile_failed",
        )
    normalized = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    return normalized if isinstance(normalized, dict) else {}


async def exchange_code_for_user(
    *,
    code: str,
    redirect_uri: str,
) -> dict[str, Any]:
    """Legacy compatibility wrapper for exchange+userinfo flow."""
    token = await exchange_code_for_token(code=code, redirect_uri=redirect_uri)
    access_token = token.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise UserCenterError(
            "User center token response did not include access_token",
            error_code="oauth_invalid_token",
        )
    normalized = await fetch_user_info(access_token)
    open_id = normalized.get("openId") or normalized.get("open_id")
    if not open_id:
        raise UserCenterError(
            "User center /user/get did not return openId",
            error_code="user_center_invalid_profile",
        )

    return {
        "openId": open_id,
        "displayName": normalized.get("displayName")
        or normalized.get("display_name")
        or normalized.get("name")
        or open_id,
        "email": normalized.get("email"),
        "avatarUrl": normalized.get("avatarUrl") or normalized.get("avatar_url"),
        "access_token": access_token,
    }


async def call_usercenter_logout(*, access_token: str) -> dict[str, Any]:
    """Call the user center's /public/logout to terminate the user-center session.

    This endpoint is provided by the user-center SDK and returns a logoutUriConfig
    mapping (app channels -> logout redirect URLs). We pass the access_token
    as a Bearer token to identify the session.
    """
    from core.settings import get_settings

    settings = get_settings()
    logout_url = f"{settings.user_center_base_uri.rstrip('/')}/public/logout"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                logout_url,
                json={},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise UserCenterError(
            "Failed to call user center logout endpoint",
            error_code="user_center_logout_failed",
        ) from exc

    logger.info("User center /public/logout response keys: %s", list(payload.keys()) if isinstance(payload, dict) else type(payload))

    if not isinstance(payload, dict):
        raise UserCenterError(
            "User center logout response is not a valid object",
            error_code="user_center_logout_failed",
        )

    # The SDK returns {respCode, respMsg, logoutUriConfig?} - treat SUCCESS as ok
    if "respCode" in payload and payload.get("respCode") != "SUCCESS":
        raise UserCenterError(
            f"User center logout error: {payload.get('respMsg', 'unknown')}",
            error_code="user_center_logout_failed",
        )

    return payload

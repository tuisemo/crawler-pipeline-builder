"""Auth API routes."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from threading import Lock
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse

from backend.auth.session import create_session, delete_session, get_session_by_token, upsert_user
from backend.auth.user_center import (
    UserCenterClient,
    UserCenterError,
    UserCenterNetworkError,
    UserCenterServerError,
    UserCenterTimeoutError,
)
from backend.core.api_response import api_response
from backend.core.settings import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

_state_lock = Lock()
_oauth_state_store: dict[str, dict[str, object]] = {}
_STATE_TTL_SECONDS = 600
_OAUTH_STATE_COOKIE_NAME = "oauth_state_nonce"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _cleanup_expired_states(now: datetime | None = None) -> None:
    current = now or _utc_now()
    with _state_lock:
        expired = [k for k, v in _oauth_state_store.items() if v["expires_at"] <= current]
        for key in expired:
            _oauth_state_store.pop(key, None)


def _store_oauth_state(state: str, next_path: str, nonce: str) -> None:
    _cleanup_expired_states()
    with _state_lock:
        _oauth_state_store[state] = {
            "next_path": next_path,
            "nonce": nonce,
            "expires_at": _utc_now() + timedelta(seconds=_STATE_TTL_SECONDS),
        }


def _consume_oauth_state(state: str, nonce: str) -> str | None:
    _cleanup_expired_states()
    with _state_lock:
        record = _oauth_state_store.get(state)
        if record is None:
            return None
        if record.get("nonce") != nonce:
            return None
        _oauth_state_store.pop(state, None)
        return str(record["next_path"])


def _is_production() -> bool:
    value = (
        os.getenv("ENV")
        or os.getenv("APP_ENV")
        or os.getenv("PYTHON_ENV")
        or ""
    ).strip().lower()
    return value in {"prod", "production"}


def _should_set_secure_cookie() -> bool:
    return _is_production()


def _build_logout_url(base_uri: str, redirect_uri: str) -> str:
    encoded_redirect = quote(redirect_uri, safe="")
    return f"{base_uri.rstrip('/')}/auth/web/#/logout?redirectUri={encoded_redirect}&channel=default"


def _sanitize_next_path(next_path: str | None) -> str:
    if not next_path:
        return "/"
    if next_path.startswith(("//", "/\\", "\\\\")):
        return "/"
    parsed = urlparse(next_path)
    if parsed.scheme or parsed.netloc:
        return "/"
    if not next_path.startswith("/"):
        return "/"
    return next_path


@router.get("/login")
def login(next: str = Query("/", alias="next")):
    """Generate OAuth state and redirect browser to user-center authorize URL."""
    settings = get_settings()
    user_center = UserCenterClient(settings)
    state = user_center.generate_state()
    nonce = secrets.token_urlsafe(32)
    next_path = _sanitize_next_path(next)
    _store_oauth_state(state, next_path, nonce)
    authorize_url = user_center.build_authorize_url(state=state, redirect_uri=settings.user_center_redirect_uri)
    response = RedirectResponse(url=authorize_url, status_code=302)
    response.set_cookie(
        key=_OAUTH_STATE_COOKIE_NAME,
        value=nonce,
        max_age=_STATE_TTL_SECONDS,
        httponly=True,
        secure=_should_set_secure_cookie(),
        samesite="lax",
        path="/",
    )
    return response


@router.get("/callback")
def callback(request: Request, code: str | None = None, state: str | None = None):
    """Validate state, exchange code, upsert user, create session, and redirect."""
    if not code or not state:
        return api_response(
            status_code=400,
            success=False,
            error_code="invalid_oauth_callback",
            error="Missing code or state in callback",
        )

    oauth_nonce = request.cookies.get(_OAUTH_STATE_COOKIE_NAME)
    if not oauth_nonce:
        return api_response(
            status_code=400,
            success=False,
            error_code="invalid_oauth_state",
            error="Invalid or expired OAuth state",
        )

    next_path = _consume_oauth_state(state, oauth_nonce)
    if next_path is None:
        return api_response(
            status_code=400,
            success=False,
            error_code="invalid_oauth_state",
            error="Invalid or expired OAuth state",
        )

    settings = get_settings()
    user_center = UserCenterClient(settings)

    try:
        token_payload = user_center.exchange_code_for_token(code)
        access_token = token_payload.get("access_token", "")
        if not access_token:
            return api_response(
                status_code=502,
                success=False,
                error_code="user_center_unavailable",
                error="登录服务暂不可用，请稍后重试",
            )
        user_details = user_center.get_user_details(access_token)
    except UserCenterServerError as exc:
        return api_response(
            status_code=502,
            success=False,
            error_code="user_center_unavailable",
            error=str(exc) or "登录服务暂不可用，请稍后重试",
            meta={"status_code": exc.status_code},
        )
    except (UserCenterTimeoutError, UserCenterNetworkError, UserCenterError):
        return api_response(
            status_code=502,
            success=False,
            error_code="user_center_unavailable",
            error="登录服务暂不可用，请稍后重试",
        )

    user = upsert_user(
        external_id=user_details.open_id,
        display_name=user_details.display_name or user_details.open_id,
        email=user_details.email,
        avatar_url=user_details.avatar_url,
    )
    raw_token = create_session(user_id=user["id"])

    response = RedirectResponse(url=next_path, status_code=302)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=_should_set_secure_cookie(),
        samesite="lax",
        path="/",
    )
    response.delete_cookie(
        key=_OAUTH_STATE_COOKIE_NAME,
        path="/",
        secure=_should_set_secure_cookie(),
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/me")
def me(request: Request):
    """Return current user info from server-side session cookie."""
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return api_response(status_code=401, success=False, error_code="not_authenticated", error="Not authenticated")

    session = get_session_by_token(token)
    if not session:
        return api_response(status_code=401, success=False, error_code="not_authenticated", error="Not authenticated")

    return api_response(
        {
            "user": {
                "id": session["user_id"],
                "display_name": session["display_name"],
                "external_id": session["external_id"],
                "openId": session["external_id"],
                "email": session.get("email"),
                "avatar_url": session.get("avatar_url"),
            }
        }
    )


@router.post("/logout")
def logout(request: Request):
    """Delete session, clear cookie, and return user-center logout URL config."""
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        delete_session(token)

    logout_url = _build_logout_url(
        settings.user_center_base_uri,
        settings.user_center_redirect_uri or "/",
    )
    response = api_response({"logoutUriConfig": {"default": logout_url}})
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=_should_set_secure_cookie(),
        httponly=True,
        samesite="lax",
    )
    return response

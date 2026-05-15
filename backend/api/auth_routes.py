"""Auth API routes backed by Authlib and Redis sessions."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from backend.auth.dependencies import AuthenticatedUser, require_auth
from backend.auth.session import (
    consume_oauth_state,
    create_session,
    derive_local_user_profile_from_token,
    delete_session,
    generate_code_verifier,
    store_oauth_state,
    upsert_user,
)
from backend.auth.user_center_client import (
    UserCenterError,
    build_authorize_url,
    call_usercenter_logout,
    exchange_code_for_token,
    fetch_user_info,
)
from backend.core.api_response import api_response
from backend.core.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])
CurrentUser = Annotated[AuthenticatedUser, Depends(require_auth)]
OAUTH_STATE_COOKIE_NAME = "crawler_workflow_oauth_state"


class ExchangeCodeRequest(BaseModel):
    code: str
    state: str


def _build_frontend_home_url(settings) -> str:
    """Build the frontend home URL for post-logout redirect."""
    return _resolve_frontend_base_url(settings) + "/#/"


def _resolve_frontend_base_url(settings) -> str:
    frontend_url = settings.user_center_frontend_url.strip()
    if frontend_url:
        return frontend_url.rstrip("/")
    parsed = urlparse(settings.user_center_redirect_uri)
    if parsed.scheme and parsed.netloc:
        path = parsed.path or ""
        callback_suffixes = ("/api/auth/callback", "/auth/callback")
        base_path = ""
        for callback_suffix in callback_suffixes:
            if path.endswith(callback_suffix):
                base_path = path[: -len(callback_suffix)]
                break
        else:
            base_path = path.rsplit("/", 1)[0]
        base_path = base_path.rstrip("/")
        return f"{parsed.scheme}://{parsed.netloc}{base_path}"
    return settings.user_center_redirect_uri.rstrip("/")


def _sanitize_next_path(next_path: str | None) -> str:
    """Normalize a next-path value, stripping any hash-prefix from SPA routes."""
    if not next_path:
        return "/"
    # Strip leading hash prefix that HashRouter may produce (#/tasks → /tasks)
    s = next_path.lstrip("#")
    if not s.startswith("/"):
        s = "/" + s
    if s.startswith(("//", "/\\", "\\\\")):
        return "/"
    parsed = urlparse(s)
    if parsed.scheme or parsed.netloc:
        return "/"
    return s


def _extract_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _resolve_access_token_expires_at(token: dict) -> str | None:
    expires_at = token.get("expires_at")
    if isinstance(expires_at, (int, float)):
        return datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()
    if isinstance(expires_at, str) and expires_at.strip():
        return expires_at
    expires_in = token.get("expires_in")
    if isinstance(expires_in, (int, float)):
        return (
            (datetime.now(timezone.utc) + timedelta(seconds=expires_in))
            .replace(microsecond=0)
            .isoformat()
        )
    return None


def _needs_refresh_soon(access_token_expires_at: str | None, skew_seconds: int = 300) -> bool:
    if not access_token_expires_at:
        return False
    try:
        expires_at = datetime.fromisoformat(access_token_expires_at)
    except ValueError:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    else:
        expires_at = expires_at.astimezone(timezone.utc)
    return (expires_at - datetime.now(timezone.utc)).total_seconds() <= skew_seconds


def _clear_oauth_state_cookie(response) -> None:
    response.delete_cookie(OAUTH_STATE_COOKIE_NAME, path="/api/auth")


def _auth_error_redirect(
    frontend_url: str, error_code: str, error_message: str
) -> RedirectResponse:
    """Build an error redirect response with the OAuth state cookie cleared."""
    response = RedirectResponse(
        url=_build_frontend_callback_error_url(frontend_url, error_code, error_message),
        status_code=302,
    )
    _clear_oauth_state_cookie(response)
    return response


@router.get("/login")
async def login(request: Request, next: str = Query("/", alias="next")):
    """Redirect the browser to the user-center authorize URL."""
    settings = get_settings()
    next_path = _sanitize_next_path(next)
    code_verifier = generate_code_verifier()
    state = store_oauth_state(next_path=next_path, code_verifier=code_verifier)
    authorize_url = build_authorize_url(
        redirect_uri=settings.user_center_redirect_uri,
        state=state,
        code_verifier=code_verifier,
    )
    response = RedirectResponse(url=authorize_url, status_code=302)
    response.set_cookie(
        key=OAUTH_STATE_COOKIE_NAME,
        value=state,
        max_age=max(settings.oauth_state_ttl_seconds, 1),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/api/auth",
    )
    return response


def _build_frontend_callback_url(
    frontend_url: str, session_id: str, next_path: str
) -> str:
    """Build the frontend hash-route callback URL with session result."""
    base = frontend_url.rstrip("/")
    next_encoded = quote(next_path, safe="")
    return f"{base}/#/auth/callback?sessionId={session_id}&nextPath={next_encoded}"


def _build_frontend_callback_error_url(
    frontend_url: str, error_code: str, error_message: str
) -> str:
    base = frontend_url.rstrip("/")
    code = quote(error_code or "auth_callback_failed", safe="")
    message = quote(error_message or "登录失败，请重试", safe="")
    return f"{base}/#/auth/callback?error={code}&errorMessage={message}"


@router.get("/callback")
async def callback(request: Request, code: str = Query(...), state: str = Query(...)):
    """OAuth callback: validate state, exchange code, create session, redirect to frontend."""
    settings = get_settings()
    frontend_url = _resolve_frontend_base_url(settings)

    state_cookie = request.cookies.get(OAUTH_STATE_COOKIE_NAME)
    if not state_cookie or state_cookie != state:
        logger.warning("OAuth callback rejected: state mismatch")
        return _auth_error_redirect(frontend_url, "invalid_oauth_state", "OAuth state is invalid or expired")

    oauth_state = consume_oauth_state(state)
    if not oauth_state:
        logger.warning("OAuth callback rejected: state consumed or missing")
        return _auth_error_redirect(frontend_url, "invalid_oauth_state", "OAuth state is invalid or expired")

    logger.info("OAuth callback received")
    try:
        token = await exchange_code_for_token(
            code=code,
            redirect_uri=settings.user_center_redirect_uri,
            code_verifier=oauth_state.get("code_verifier"),
        )
    except UserCenterError as exc:
        logger.warning(
            "OAuth callback exchange failed: error_code=%s, message=%s",
            exc.error_code,
            str(exc),
        )
        return _auth_error_redirect(frontend_url, exc.error_code, "登录失败，请重试")

    user_details = derive_local_user_profile_from_token(token)
    logger.info(
        "OAuth callback: token-derived external_id=%s (source=token_claims)",
        user_details.get("external_id"),
    )

    # Always verify/override with user center API — it is the authoritative source of openId
    try:
        profile = await fetch_user_info(token.get("access_token", ""))
        api_open_id = profile.get("openId") or profile.get("open_id")
        if api_open_id:
            api_open_id = str(api_open_id)
            token_open_id = user_details.get("external_id")
            if token_open_id and token_open_id != api_open_id:
                logger.warning(
                    "OAuth callback: external_id mismatch — token=%s api=%s, using api openId",
                    token_open_id, api_open_id,
                )
            user_details = {
                "external_id": api_open_id,
                "display_name": (
                    profile.get("personName")
                    or profile.get("displayName")
                    or profile.get("nickName")
                    or user_details.get("display_name")
                    or api_open_id
                ),
                "email": profile.get("email") or user_details.get("email"),
                "avatar_url": profile.get("imageUrl") or user_details.get("avatar_url"),
            }
            logger.info(
                "OAuth callback: resolved external_id=%s (source=user_center_api)",
                api_open_id,
            )
    except UserCenterError as exc:
        logger.warning("User center user info API failed, using token-derived identity: %s", exc)

    if not user_details.get("external_id"):
        logger.warning("OAuth callback missing openId from all sources")
        return _auth_error_redirect(frontend_url, "oauth_subject_missing", "登录失败，请重试")
    external_id = user_details["external_id"]
    display_name = user_details["display_name"]

    user = upsert_user(
        external_id=external_id,
        display_name=display_name,
        email=user_details.get("email"),
        avatar_url=user_details.get("avatar_url"),
    )

    session_id = create_session(
        user_id=user["id"],
        access_token=token.get("access_token"),
        refresh_token=token.get("refresh_token"),
        access_token_expires_at=_resolve_access_token_expires_at(token),
        user_row=user,
    )

    next_path = oauth_state.get("next_path") or "/"
    redirect_url = _build_frontend_callback_url(frontend_url, session_id, next_path)
    logger.info(
        "OAuth callback success: user_id=%s external_id=%s next_path=%s",
        user["id"],
        external_id,
        next_path,
    )

    response = RedirectResponse(url=redirect_url, status_code=302)
    _clear_oauth_state_cookie(response)
    return response


@router.get("/me")
def me(current_user: CurrentUser):
    """Return current user info from the Redis-backed app session."""
    return api_response(
        {
            "user": {
                "id": current_user.user_id,
                "display_name": current_user.display_name,
                "external_id": current_user.external_id,
                "openId": current_user.external_id,
                "email": current_user.email,
                "avatar_url": current_user.avatar_url,
            },
            "auth": {
                "session_status": current_user.token_status or "active",
                "token_expires_at": current_user.access_token_expires_at,
                "needs_refresh_soon": _needs_refresh_soon(current_user.access_token_expires_at),
                "has_refresh_token": current_user.refresh_token_present,
            },
        }
    )


@router.post("/logout")
async def logout(current_user: CurrentUser):
    """Delete the local app session and notify the user-center gateway.

    1. Reads the Redis session to obtain the user-center access_token.
    2. Calls the user-center ``/public/logout`` endpoint so the gateway
       can clean up its ``x-session-id`` session in Redis.
    3. Destroys the sea-data Redis session.
    4. Returns ``loggedOut: True`` — the frontend clears local state
       and navigates home.

    Note: the user-center's Spring Security SSO session (JSESSIONID) is
    maintained on the user-center domain and cannot be cleared via
    server-to-server calls.  It expires naturally based on its TTL.
    Direct browser navigation to the user-center ``/logout`` is not
    possible because the gateway ``SessionInterceptor`` blocks requests
    that lack an ``x-session-id`` header (E201).
    """
    from backend.auth.session import get_session_by_token

    # Read session before deletion to obtain the user-center access_token
    raw_session = get_session_by_token(current_user.session_id or "")
    access_token = raw_session.get("access_token") if raw_session else None

    # Best-effort: notify user-center /public/logout so the gateway
    # can clean up its x-session-id Redis entry.
    if access_token:
        try:
            await call_usercenter_logout(access_token=access_token)
            logger.info("User center gateway logout completed for user_id=%s", current_user.user_id)
        except (UserCenterError, Exception) as exc:
            logger.warning("User center gateway logout failed (non-fatal): %s", exc)

    delete_session(current_user.session_id)

    return api_response({
        "loggedOut": True,
    })


@router.get("/logout")
async def logout_redirect(request: Request):
    """Browser-initiated full logout: delete local session then redirect to
    the frontend home page.

    Flow:
      1. Browser hits GET /api/auth/logout?sessionId=<token>
      2. Delete local Redis session
      3. Best-effort: notify user-center /public/logout to clean gateway session
      4. Redirect browser to the frontend home page

    Note: the user-center's Spring Security SSO session (JSESSIONID) cannot
    be cleared via browser redirect because the gateway SessionInterceptor
    blocks requests that lack an x-session-id header. The SSO session
    expires naturally based on its TTL. The key defence against auto-re-login
    is that the frontend logoutFn navigates away via window.location.href
    BEFORE any React state update that would trigger RequireAuth → login().
    """
    settings = get_settings()
    frontend_home_url = _build_frontend_home_url(settings)

    # Accept session token from query param (browser redirect) or Authorization header
    token = request.query_params.get("sessionId") or _extract_bearer_token(request)

    # Read session before deletion to obtain the user-center access_token
    raw_session = None
    if token:
        from backend.auth.session import get_session_by_token
        raw_session = get_session_by_token(token)
        delete_session(token)

    # Best-effort: notify user-center /public/logout to clean gateway x-session-id
    access_token = raw_session.get("access_token") if raw_session else None
    if access_token:
        try:
            await call_usercenter_logout(access_token=access_token)
            logger.info("User center gateway logout completed (GET logout)")
        except (UserCenterError, Exception) as exc:
            logger.warning("User center gateway logout failed (non-fatal, GET): %s", exc)

    logger.info("Redirecting to frontend home after logout: %s", frontend_home_url)
    return RedirectResponse(url=frontend_home_url, status_code=302)

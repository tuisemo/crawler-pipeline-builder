"""Auth API routes backed by Authlib and Redis sessions."""

from __future__ import annotations

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
    exchange_code_for_token,
    fetch_user_info,
)
from backend.core.api_response import api_response
from backend.core.settings import get_settings

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
        callback_suffix = "/api/auth/callback"
        if path.endswith(callback_suffix):
            base_path = path[: -len(callback_suffix)]
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
    import logging

    logger = logging.getLogger(__name__)
    settings = get_settings()
    frontend_url = _resolve_frontend_base_url(settings)

    state_cookie = request.cookies.get(OAUTH_STATE_COOKIE_NAME)
    if not state_cookie or state_cookie != state:
        logger.warning("OAuth callback rejected: state mismatch")
        response = RedirectResponse(
            url=_build_frontend_callback_error_url(
                frontend_url,
                "invalid_oauth_state",
                "OAuth state is invalid or expired",
            ),
            status_code=302,
        )
        _clear_oauth_state_cookie(response)
        return response

    oauth_state = consume_oauth_state(state)
    if not oauth_state:
        logger.warning("OAuth callback rejected: state consumed or missing")
        response = RedirectResponse(
            url=_build_frontend_callback_error_url(
                frontend_url,
                "invalid_oauth_state",
                "OAuth state is invalid or expired",
            ),
            status_code=302,
        )
        _clear_oauth_state_cookie(response)
        return response

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
        response = RedirectResponse(
            url=_build_frontend_callback_error_url(
                frontend_url,
                exc.error_code,
                "登录失败，请重试",
            ),
            status_code=302,
        )
        _clear_oauth_state_cookie(response)
        return response

    user_details = derive_local_user_profile_from_token(token)
    if not user_details.get("external_id"):
        # Token lacks open_id — fallback to user center /server/public/user/get
        logger.info("Token has no open_id, falling back to user center user info endpoint")
        try:
            profile = await fetch_user_info(token.get("access_token", ""))
            open_id = profile.get("openId") or profile.get("open_id")
            if open_id:
                user_details = {
                    "external_id": str(open_id),
                    "display_name": profile.get("personName")
                    or profile.get("displayName")
                    or profile.get("nickName")
                    or str(open_id),
                    "email": profile.get("email"),
                    "avatar_url": profile.get("imageUrl"),
                }
        except UserCenterError as exc:
            logger.warning("User center user info fallback failed: %s", exc)

    if not user_details.get("external_id"):
        logger.warning("OAuth callback missing stable subject in token claims")
        response = RedirectResponse(
            url=_build_frontend_callback_error_url(
                frontend_url,
                "oauth_subject_missing",
                "登录失败，请重试",
            ),
            status_code=302,
        )
        _clear_oauth_state_cookie(response)
        return response
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
async def logout(request: Request, current_user: CurrentUser):
    """Delete the local app session.

    Deletes the local Redis session. The frontend should then
    redirect the user to the user-center web logout page to
    terminate the user-center session.
    """
    import logging

    logger = logging.getLogger(__name__)

    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    settings = get_settings()
    delete_session(token)

    # Build user-center web logout URL so the frontend can redirect
    uc_logout_url = (
        f"{settings.user_center_base_uri.rstrip('/')}/auth/web/#/logout"
        f"?redirectUri={quote(settings.user_center_frontend_url, safe='')}"
        f"&channel={settings.user_center_client_id}"
    )

    return api_response({
        "loggedOut": True,
        "logoutUriConfig": {settings.user_center_client_id: uc_logout_url},
    })


@router.get("/logout")
async def logout_redirect(request: Request):
    """Browser-initiated logout: delete session and redirect to user-center logout."""
    settings = get_settings()

    token = _extract_bearer_token(request)
    if token:
        delete_session(token)

    # Redirect to user-center web logout page
    uc_logout_url = (
        f"{settings.user_center_base_uri.rstrip('/')}/auth/web/#/logout"
        f"?redirectUri={quote(settings.user_center_frontend_url, safe='')}"
        f"&channel={settings.user_center_client_id}"
    )
    return RedirectResponse(url=uc_logout_url, status_code=302)

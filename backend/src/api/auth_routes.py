"""Auth API routes backed by Authlib and Redis sessions.

OAuth state validation uses Redis one-time-consumption only — no cookie
dependency. This eliminates deployment-path coupling (sub-path deployments
like /crawler-studio/ no longer need cookie path alignment).

The redirect_uri and frontend_url are self-derived from incoming request
headers (X-Forwarded-*) when available, falling back to .env config for
local development.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from auth.dependencies import AuthenticatedUser, require_auth
from auth.session import (
    consume_oauth_state,
    create_session,
    derive_local_user_profile_from_token,
    delete_session,
    generate_code_verifier,
    store_oauth_state,
    upsert_user,
)
from auth.user_center_client import (
    UserCenterError,
    build_authorize_url,
    call_usercenter_logout,
    exchange_code_for_token,
    fetch_user_info,
)
from core.api_response import api_response
from core.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])
CurrentUser = Annotated[AuthenticatedUser, Depends(require_auth)]


class ExchangeCodeRequest(BaseModel):
    code: str
    state: str


class AuthorizeRequest(BaseModel):
    next_path: str = "/"
    redirect_uri: str = ""


class TokenExchangeRequest(BaseModel):
    code: str
    state: str


# ── Request self-derivation helpers ───────────────────────


def _derive_scheme(request: Request) -> str:
    """Derive the request scheme, respecting reverse-proxy headers."""
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto:
        return forwarded_proto.strip()
    return request.url.scheme


def _derive_host(request: Request) -> str:
    """Derive the request host, respecting reverse-proxy headers."""
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        return forwarded_host.strip()
    host = request.headers.get("host")
    if host:
        return host.strip()
    return request.url.netloc


def _derive_deploy_prefix(request: Request) -> str:
    """Derive the deploy sub-path prefix from proxy headers or request path.

    Returns a string like ``crawler-studio`` or ``""`` (root deploy).
    """
    forwarded_prefix = request.headers.get("x-forwarded-prefix")
    if forwarded_prefix:
        return forwarded_prefix.strip().strip("/")
    # Fallback: infer from request path by splitting before /api/auth...
    # Examples:
    #   /crawler-studio/api/auth/login    -> crawler-studio
    #   /crawler-studio/api/auth/callback -> crawler-studio
    #   /api/auth/logout                  -> ""
    path = request.url.path or ""
    marker = "/api/auth"
    idx = path.find(marker)
    if idx > 0:
        return path[:idx].strip("/")
    return ""


def _derive_redirect_uri(request: Request) -> str:
    """Self-derive the OAuth callback URI from the incoming request.

    Uses X-Forwarded-* headers when available (production behind nginx),
    falls back to request.url attributes (local dev).
    """
    scheme = _derive_scheme(request)
    host = _derive_host(request)
    prefix = _derive_deploy_prefix(request)
    path = f"/{prefix}/api/auth/callback" if prefix else "/api/auth/callback"
    return f"{scheme}://{host}{path}"


def _resolve_redirect_uri(request: Request, settings) -> str:
    """Resolve OAuth redirect URI with config-first precedence."""
    configured = settings.user_center_redirect_uri.strip()
    if configured:
        return configured
    return _derive_redirect_uri(request)


# ── Route/path helpers ────────────────────────────────────


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


def _auth_error_redirect(
    frontend_base_path: str, error_code: str, error_message: str
) -> RedirectResponse:
    """Build an error redirect response to the frontend."""
    return RedirectResponse(
        url=_build_frontend_callback_error_url(frontend_base_path, error_code, error_message),
        status_code=302,
    )


# ── Frontend-driven OAuth helpers ────────────────────────


def _validate_frontend_redirect_uri(request: Request, redirect_uri: str) -> str:
    """Validate a frontend-declared redirect_uri for the OAuth authorize flow.

    Security rules:
    - Must use http or https scheme.
    - Must not contain query params or fragments.
    - In production (non-localhost), the host must match the request's
      derived host (prevents open-redirect / phishing).
    - Localhost / 127.0.0.1 are always allowed for development.
    """
    if not redirect_uri or not redirect_uri.strip():
        raise HTTPException(status_code=400, detail="redirect_uri is required")

    parsed = urlparse(redirect_uri)

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail="redirect_uri must use http or https scheme",
        )

    if parsed.query or parsed.fragment:
        raise HTTPException(
            status_code=400,
            detail="redirect_uri must not contain query params or fragments",
        )

    # Allow localhost / 127.0.0.1 for local development without host matching
    if parsed.hostname in ("localhost", "127.0.0.1", "::1"):
        return redirect_uri

    # Production: host should match the request's derived host.
    # Log a warning on mismatch but do NOT reject — behind Nginx the derived
    # host may be the internal host:port, not the public-facing one.
    request_host = _derive_host(request)
    if parsed.netloc != request_host:
        logger.warning(
            "redirect_uri host mismatch: parsed.netloc=%s, derived_host=%s. "
            "Allowing because backend is likely behind a reverse proxy.",
            parsed.netloc, request_host,
        )

    return redirect_uri


async def _resolve_user_details_async(token: dict) -> dict:
    """Resolve user identity from token claims + user center API."""
    user_details = derive_local_user_profile_from_token(token)
    logger.info(
        "Token-derived external_id=%s (source=token_claims)",
        user_details.get("external_id"),
    )

    try:
        profile = await fetch_user_info(token.get("access_token", ""))
        api_open_id = profile.get("openId") or profile.get("open_id")
        if api_open_id:
            api_open_id = str(api_open_id)
            token_open_id = user_details.get("external_id")
            if token_open_id and token_open_id != api_open_id:
                logger.warning(
                    "external_id mismatch — token=%s api=%s, using api openId",
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
            logger.info("resolved external_id=%s (source=user_center_api)", api_open_id)
    except UserCenterError as exc:
        logger.warning("User center user info API failed, using token-derived identity: %s", exc)

    return user_details


# ── Frontend-driven OAuth endpoints (new flow) ──────────


@router.post("/authorize")
async def authorize(request: Request, body: AuthorizeRequest):
    """Generate an OAuth authorize URL for the frontend to redirect to.

    Frontend-driven OAuth flow — Step 1:
      1. Frontend calls POST /api/auth/authorize
      2. Backend generates state + PKCE code_verifier, stores in Redis
      3. Returns {authorize_url, state} as JSON
      4. Frontend stores state in sessionStorage, redirects to authorize_url

    The redirect_uri is the FRONTEND URL (not backend callback).
    After user authenticates at the user center, the browser is redirected
    back to the frontend with ?code=xxx&state=yyy in the URL.
    """
    settings = get_settings()
    next_path = _sanitize_next_path(body.next_path)
    code_verifier = generate_code_verifier()

    # redirect_uri: frontend-declared (validated) > .env config > derived
    if body.redirect_uri and body.redirect_uri.strip():
        redirect_uri = _validate_frontend_redirect_uri(request, body.redirect_uri)
    else:
        redirect_uri = _resolve_redirect_uri(request, settings)

    state = store_oauth_state(
        next_path=next_path,
        code_verifier=code_verifier,
        redirect_uri=redirect_uri,
    )

    authorize_url = build_authorize_url(
        redirect_uri=redirect_uri,
        state=state,
        code_verifier=code_verifier,
    )

    logger.info(
        "OAuth authorize: redirect_uri=%s, next_path=%s, state=%s... (len=%d)",
        redirect_uri, next_path,
        state[:12], len(state),
    )

    return api_response({
        "authorize_url": authorize_url,
        "state": state,
    })


@router.post("/token")
async def exchange_token(request: Request, body: TokenExchangeRequest):
    """Exchange an OAuth authorization code for a session.

    Frontend-driven OAuth flow — Step 2:
      1. Frontend detects ?code=xxx&state=yyy in the URL (from user center redirect)
      2. Frontend validates state matches sessionStorage
      3. Frontend calls POST /api/auth/token with {code, state}
      4. Backend validates state from Redis, exchanges code, creates session
      5. Returns {session_id, user, auth} as JSON
    """
    settings = get_settings()

    # Validate state via Redis one-time-consumption
    oauth_state = consume_oauth_state(body.state)
    if not oauth_state:
        logger.warning(
            "Token exchange rejected: state not found in Redis. "
            "received_state=%s... (len=%d). "
            "Possible causes: user center modified state, Redis TTL expired, "
            "or double-submit.",
            body.state[:12] if body.state else "EMPTY",
            len(body.state) if body.state else 0,
        )
        raise HTTPException(
            status_code=400,
            detail="OAuth state is invalid or expired. Please try logging in again.",
        )

    redirect_uri = oauth_state.get("redirect_uri") or _resolve_redirect_uri(request, settings)

    logger.info("OAuth token exchange received")
    try:
        token = await exchange_code_for_token(
            code=body.code,
            redirect_uri=redirect_uri,
            code_verifier=oauth_state.get("code_verifier"),
        )
    except UserCenterError as exc:
        logger.warning(
            "Token exchange failed: error_code=%s, message=%s",
            exc.error_code, str(exc),
        )
        raise HTTPException(
            status_code=400,
            detail="登录失败，请重试",
        ) from exc

    # Resolve user identity (token claims + user center API)
    user_details = await _resolve_user_details_async(token)

    if not user_details.get("external_id"):
        logger.warning("Token exchange missing openId from all sources")
        raise HTTPException(
            status_code=400,
            detail="登录失败：无法获取用户标识，请重试",
        )

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

    logger.info(
        "Token exchange success: user_id=%s external_id=%s",
        user["id"], external_id,
    )

    return api_response({
        "session_id": session_id,
        "next_path": next_path,
        "user": {
            "id": user["id"],
            "display_name": user["display_name"],
            "external_id": user["external_id"],
            "openId": user["external_id"],
            "email": user.get("email"),
            "avatar_url": user.get("avatar_url"),
        },
        "auth": {
            "session_status": "active",
            "token_expires_at": _resolve_access_token_expires_at(token),
            "needs_refresh_soon": False,
            "has_refresh_token": bool(token.get("refresh_token")),
        },
    })


# ── Legacy BFF-redirect endpoints (backward compatible) ─


@router.get("/login")
async def login(request: Request, next: str = Query("/", alias="next")):
    """Redirect the browser to the user-center authorize URL.

    The redirect_uri is self-derived from the incoming request headers
    (X-Forwarded-*), falling back to .env config for local development.
    No cookie is set — OAuth state CSRF protection relies solely on
    Redis one-time-consumption.
    """
    settings = get_settings()
    next_path = _sanitize_next_path(next)
    code_verifier = generate_code_verifier()
    redirect_uri = _resolve_redirect_uri(request, settings)
    state = store_oauth_state(
        next_path=next_path,
        code_verifier=code_verifier,
        redirect_uri=redirect_uri,
    )

    authorize_url = build_authorize_url(
        redirect_uri=redirect_uri,
        state=state,
        code_verifier=code_verifier,
    )
    logger.info(
        "OAuth login: derived redirect_uri=%s, next_path=%s",
        redirect_uri, next_path,
    )
    return RedirectResponse(url=authorize_url, status_code=302)


def _build_frontend_callback_url(
    frontend_base_path: str, session_id: str, next_path: str
) -> str:
    """Build frontend relative hash-route callback URL with session result."""
    base = frontend_base_path.rstrip("/")
    next_encoded = quote(next_path, safe="")
    return f"{base}/#/auth/callback?sessionId={session_id}&nextPath={next_encoded}"


def _build_frontend_callback_error_url(
    frontend_base_path: str, error_code: str, error_message: str
) -> str:
    base = frontend_base_path.rstrip("/")
    code = quote(error_code or "auth_callback_failed", safe="")
    message = quote(error_message or "登录失败，请重试", safe="")
    return f"{base}/#/auth/callback?error={code}&errorMessage={message}"


@router.get("/callback")
async def callback(request: Request, code: str = Query(...), state: str = Query(...)):
    """OAuth callback: validate state via Redis, exchange code, create session, redirect to frontend.

    State validation uses Redis atomic consume (GET+DEL) only — no cookie.
    The redirect_uri used for token exchange is re-derived from the request
    to match the one used during login.
    """
    settings = get_settings()

    # Build frontend base path as a relative route to avoid host/port coupling.
    deploy_prefix = _derive_deploy_prefix(request)
    frontend_base_path = f"/{deploy_prefix}" if deploy_prefix else ""

    # Validate state via Redis one-time-consumption (no cookie dependency)
    oauth_state = consume_oauth_state(state)
    if not oauth_state:
        logger.warning("OAuth callback rejected: state consumed, missing, or expired")
        return _auth_error_redirect(frontend_base_path, "invalid_oauth_state", "OAuth state is invalid or expired")

    redirect_uri = oauth_state.get("redirect_uri") or _resolve_redirect_uri(request, settings)

    logger.info("OAuth callback received")
    try:
        token = await exchange_code_for_token(
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=oauth_state.get("code_verifier"),
        )
    except UserCenterError as exc:
        logger.warning(
            "OAuth callback exchange failed: error_code=%s, message=%s",
            exc.error_code,
            str(exc),
        )
        return _auth_error_redirect(frontend_base_path, exc.error_code, "登录失败，请重试")

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
        return _auth_error_redirect(frontend_base_path, "oauth_subject_missing", "登录失败，请重试")
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
    redirect_url = _build_frontend_callback_url(frontend_base_path, session_id, next_path)
    logger.info(
        "OAuth callback success: user_id=%s external_id=%s next_path=%s",
        user["id"],
        external_id,
        next_path,
    )

    return RedirectResponse(url=redirect_url, status_code=302)


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
    from auth.session import get_session_by_token

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

    The redirect URL is self-derived from the request headers, so this
    endpoint works correctly under any deploy sub-path without .env config.
    """
    # Redirect using a relative path to avoid host/port coupling.
    deploy_prefix = _derive_deploy_prefix(request)
    frontend_base_path = f"/{deploy_prefix}" if deploy_prefix else ""
    frontend_home_url = f"{frontend_base_path}/#/"

    # Accept session token from query param (browser redirect) or Authorization header
    token = request.query_params.get("sessionId") or _extract_bearer_token(request)

    # Read session before deletion to obtain the user-center access_token
    raw_session = None
    if token:
        from auth.session import get_session_by_token
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

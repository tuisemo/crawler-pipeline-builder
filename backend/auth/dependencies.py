"""FastAPI dependency injection for authentication.

Provides:
- get_current_user: reads the Authorization bearer header, validates session, returns user object or raises 401
- require_auth: forces authentication on any route it's applied to
- require_task_access: checks that current user owns the specified task, returns 404 if not owner

These dependencies are used to protect /api/workflows/* and /api/assist/* routes.
Public endpoints (/, /static/*, /api/auth/*) are NOT protected.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from backend.auth.session import get_session_by_token, session_needs_refresh, update_session
from backend.auth.user_center_client import UserCenterError, refresh_access_token


# ── Data models ───────────────────────────────────────────────────────────


class AuthenticatedUser:
    """Lightweight user object extracted from a valid session."""

    __slots__ = (
        "user_id",
        "external_id",
        "display_name",
        "email",
        "avatar_url",
        "session_id",
        "token_status",
        "access_token_expires_at",
        "refresh_token_present",
    )

    def __init__(
        self,
        *,
        user_id: int,
        external_id: str,
        display_name: str,
        email: str | None = None,
        avatar_url: str | None = None,
        session_id: str | None = None,
        token_status: str | None = None,
        access_token_expires_at: str | None = None,
        refresh_token_present: bool = False,
    ) -> None:
        self.user_id = user_id
        self.external_id = external_id
        self.display_name = display_name
        self.email = email
        self.avatar_url = avatar_url
        self.session_id = session_id
        self.token_status = token_status
        self.access_token_expires_at = access_token_expires_at
        self.refresh_token_present = refresh_token_present

    def __repr__(self) -> str:
        return f"AuthenticatedUser(user_id={self.user_id}, display_name={self.display_name!r})"


# ── Dependencies ─────────────────────────────────────────────────────────


async def _resolve_authenticated_session(raw_token: str) -> dict:
    session = get_session_by_token(raw_token)
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if session.get("token_status") in {"revoked", "expired", "refresh_failed"}:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not session_needs_refresh(session):
        update_session(
            raw_token,
            last_seen_at=datetime.now(timezone.utc).isoformat(),
        )
        return get_session_by_token(raw_token) or session

    refresh_token = session.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        update_session(
            raw_token,
            token_status="expired",
            last_seen_at=datetime.now(timezone.utc).isoformat(),
        )
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        refreshed = await refresh_access_token(refresh_token)
    except UserCenterError:
        update_session(
            raw_token,
            token_status="refresh_failed",
            last_seen_at=datetime.now(timezone.utc).isoformat(),
        )
        raise HTTPException(status_code=401, detail="Not authenticated")

    expires_at = refreshed.get("expires_at")
    if isinstance(expires_at, (int, float)):
        expires_at_iso = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()
    else:
        expires_in = refreshed.get("expires_in")
        expires_at_iso = (
            (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
            if isinstance(expires_in, (int, float))
            else session.get("access_token_expires_at")
        )
    updated = update_session(
        raw_token,
        access_token=refreshed.get("access_token"),
        refresh_token=refreshed.get("refresh_token") or refresh_token,
        access_token_expires_at=expires_at_iso,
        token_status="active",
        token_checked_at=datetime.now(timezone.utc).isoformat(),
        last_seen_at=datetime.now(timezone.utc).isoformat(),
    )
    return updated or get_session_by_token(raw_token) or session


async def get_current_user(request: Request) -> AuthenticatedUser:
    """Extract and validate the Authorization bearer token from the request.

    Raises:
        HTTPException(401): If the Authorization header is missing,
            malformed, or references an unknown session.
    """
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )

    session = await _resolve_authenticated_session(token.strip())

    return AuthenticatedUser(
        user_id=session["user_id"],
        external_id=session["external_id"],
        display_name=session["display_name"],
        email=session.get("email"),
        avatar_url=session.get("avatar_url"),
        session_id=session.get("session_id"),
        token_status=session.get("token_status"),
        access_token_expires_at=session.get("access_token_expires_at"),
        refresh_token_present=bool(session.get("refresh_token")),
    )


async def require_auth(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    """Require that the request is authenticated.

    This is a pass-through dependency that simply uses get_current_user
    to force authentication on any route it's applied to.
    """
    return current_user


async def require_task_access(
    task_id: int,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    """Verify that the current user owns the specified task.

    Args:
        task_id: The ID of the task to check ownership for.
        current_user: The authenticated user (injected by require_auth).

    Returns:
        The AuthenticatedUser if the user owns the task.

    Raises:
        HTTPException(404): If the task does not exist OR the user does
            not own it. Returns 404 (not 403) to prevent task-ID
            enumeration.
    """
    # Import here to avoid circular imports at module load time
    from backend.database import get_cursor

    with get_cursor() as cur:
        cur.execute(
            "SELECT owner_user_id FROM tasks WHERE id = %s",
            (task_id,),
        )
        row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if row["owner_user_id"] != current_user.user_id:
        # Return 404 to avoid disclosing existence of other users' tasks
        raise HTTPException(status_code=404, detail="Task not found")

    return current_user


# ── Type aliases for convenient route injection ───────────────────────────

CurrentUser = Annotated[AuthenticatedUser, Depends(require_auth)]
TaskAccessUser = Annotated[AuthenticatedUser, Depends(require_task_access)]

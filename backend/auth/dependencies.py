"""FastAPI dependency injection for authentication.

Provides:
- get_current_user: reads session cookie, validates session, returns user object or raises 401
- require_auth: forces authentication on any route it's applied to
- require_task_access: checks that current user owns the specified task, returns 404 if not owner

These dependencies are used to protect /api/workflows/* and /api/assist/* routes.
Public endpoints (/, /static/*, /api/auth/*) are NOT protected.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from backend.auth.session import get_session_by_token
from backend.core.settings import get_settings


# ── Data models ───────────────────────────────────────────────────────────


class AuthenticatedUser:
    """Lightweight user object extracted from a valid session."""

    __slots__ = ("user_id", "external_id", "display_name", "email", "avatar_url")

    def __init__(
        self,
        *,
        user_id: int,
        external_id: str,
        display_name: str,
        email: str | None = None,
        avatar_url: str | None = None,
    ) -> None:
        self.user_id = user_id
        self.external_id = external_id
        self.display_name = display_name
        self.email = email
        self.avatar_url = avatar_url

    def __repr__(self) -> str:
        return f"AuthenticatedUser(user_id={self.user_id}, display_name={self.display_name!r})"


# ── Dependencies ─────────────────────────────────────────────────────────


async def get_current_user(request: Request) -> AuthenticatedUser:
    """Extract and validate the session cookie from the request.

    Reads the session cookie (name configured via SESSION_COOKIE_NAME),
    hashes it, looks up the session in the database, checks expiry, and
    returns an AuthenticatedUser if valid.

    Raises:
        HTTPException(401): If no cookie is present, or the session is
            invalid, expired, or forged.
    """
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )

    session = get_session_by_token(token)
    if not session:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )

    return AuthenticatedUser(
        user_id=session["user_id"],
        external_id=session["external_id"],
        display_name=session["display_name"],
        email=session.get("email"),
        avatar_url=session.get("avatar_url"),
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

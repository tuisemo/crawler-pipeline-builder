"""Backend auth module — session management and user center integration."""

from auth.dependencies import (
    AuthenticatedUser,
    CurrentUser,
    TaskAccessUser,
    get_current_user,
    require_auth,
    require_task_access,
)
from auth.session import (
    create_session,
    delete_session,
    get_session_by_token,
    upsert_user,
)

__all__ = [
    "AuthenticatedUser",
    "CurrentUser",
    "TaskAccessUser",
    "create_session",
    "delete_session",
    "get_current_user",
    "get_session_by_token",
    "require_auth",
    "require_task_access",
    "upsert_user",
]


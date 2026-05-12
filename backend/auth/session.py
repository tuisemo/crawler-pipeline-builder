"""Session and user management service.

Provides:
- upsert_user: creates or updates a local user mirror from user center data
- create_session: generates a cryptographically random token, stores its
  SHA-256 hash in the DB, and returns the raw token
- get_session_by_token: validates a session token and returns user info
- delete_session: removes a session (for logout)
- cleanup_expired_sessions: removes all expired sessions from the DB

Security invariants:
- Token is generated using secrets.token_urlsafe (>= 32 bytes of entropy)
- Only the SHA-256 hash of the token is stored in the database
- Expired sessions are treated as invalid (return None)
- Non-existent / forged tokens return None (no information leakage)
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.core.settings import get_settings
from backend.database import get_cursor


# ── Token helpers ─────────────────────────────────────────────────────────

_TOKEN_ENTROPY_BYTES = 32  # 256 bits of entropy


def _generate_token() -> str:
    """Generate a cryptographically random session token.

    Uses ``secrets.token_urlsafe`` with at least 32 bytes of entropy,
    producing a URL-safe base64 string.
    """
    return secrets.token_urlsafe(_TOKEN_ENTROPY_BYTES)


def _hash_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest of a raw session token."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# ── User management ──────────────────────────────────────────────────────


def upsert_user(
    *,
    external_id: str,
    display_name: str,
    email: str | None = None,
    avatar_url: str | None = None,
) -> dict[str, Any]:
    """Create a new user or update an existing one.

    If a user with the given ``external_id`` already exists, their
    ``display_name``, ``email``, ``avatar_url``, and ``synced_at`` are
    updated. Otherwise, a new user row is inserted.

    Args:
        external_id: Unique identifier from the user center (openId).
        display_name: Human-readable name for display.
        email: User email address (optional).
        avatar_url: URL to user avatar image (optional).

    Returns:
        Dict with the upserted user's fields (id, external_id,
        display_name, email, avatar_url, synced_at, created_at).
    """
    now = datetime.now(timezone.utc)

    with get_cursor() as cur:
        # Check if user exists
        cur.execute(
            "SELECT id FROM users WHERE external_id = %s",
            (external_id,),
        )
        existing = cur.fetchone()

        if existing:
            # Update existing user
            cur.execute(
                """UPDATE users
                   SET display_name = %s,
                       email = %s,
                       avatar_url = %s,
                       synced_at = %s
                   WHERE external_id = %s""",
                (display_name, email, avatar_url, now, external_id),
            )
        else:
            # Insert new user
            cur.execute(
                """INSERT INTO users (external_id, display_name, email, avatar_url, synced_at)
                   VALUES (%s, %s, %s, %s, %s)""",
                (external_id, display_name, email, avatar_url, now),
            )

        # Fetch the full user record
        cur.execute(
            "SELECT id, external_id, display_name, email, avatar_url, synced_at, created_at "
            "FROM users WHERE external_id = %s",
            (external_id,),
        )
        return cur.fetchone()


# ── Session management ───────────────────────────────────────────────────


def create_session(
    *,
    user_id: int,
    ttl_hours: int | None = None,
) -> str:
    """Create a new session for the given user.

    Generates a cryptographically random token, stores its SHA-256 hash
    in the ``sessions`` table along with the ``user_id`` and an
    ``expires_at`` timestamp, and returns the raw token (which should
    be set as an HttpOnly cookie).

    Args:
        user_id: The local user ID to associate the session with.
        ttl_hours: Override the default session TTL (from settings).
                   Falls back to ``settings.session_ttl_hours`` if None.

    Returns:
        The raw session token (to be set as a cookie value).
    """
    settings = get_settings()
    effective_ttl = ttl_hours if ttl_hours is not None else settings.session_ttl_hours

    raw_token = _generate_token()
    token_hash = _hash_token(raw_token)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=effective_ttl)

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO sessions (user_id, token_hash, created_at, expires_at)
               VALUES (%s, %s, %s, %s)""",
            (user_id, token_hash, now, expires_at),
        )

    return raw_token


def get_session_by_token(raw_token: str) -> dict[str, Any] | None:
    """Look up a session by its raw token value.

    Hashes the provided token, queries the ``sessions`` table, checks
    expiry, and—if valid—returns the associated user information.

    Args:
        raw_token: The raw session token (as received from the cookie).

    Returns:
        A dict with ``user_id``, ``external_id``, ``display_name``,
        ``email``, ``avatar_url``, ``session_id``, and ``expires_at``
        if the session is valid and not expired; ``None`` otherwise.
    """
    token_hash = _hash_token(raw_token)
    now = datetime.now(timezone.utc)

    with get_cursor() as cur:
        cur.execute(
            """SELECT s.id AS session_id, s.user_id, s.expires_at,
                      u.external_id, u.display_name, u.email, u.avatar_url
               FROM sessions s
               JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = %s""",
            (token_hash,),
        )
        row = cur.fetchone()

    if row is None:
        return None

    # Check expiry
    expires_at = row["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at <= now:
        return None

    return row


def delete_session(raw_token: str) -> None:
    """Delete a session by its raw token value.

    Used for logout. If the token does not match any session, this is
    a no-op (does not raise).

    Args:
        raw_token: The raw session token (as received from the cookie).
    """
    token_hash = _hash_token(raw_token)

    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM sessions WHERE token_hash = %s",
            (token_hash,),
        )


def cleanup_expired_sessions() -> int:
    """Remove all expired sessions from the database.

    Deletes every session row where ``expires_at < NOW()``.

    Returns:
        The number of deleted session rows.
    """
    now = datetime.now(timezone.utc)

    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM sessions WHERE expires_at < %s",
            (now,),
        )
        return cur.rowcount

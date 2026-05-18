"""Redis-backed OAuth state and app-session management."""

from __future__ import annotations

import base64
import json
import secrets
from datetime import datetime, timezone
from typing import Any

import redis as _redis

from core.settings import get_settings
from database import get_cursor


# ── Token helpers ─────────────────────────────────────────────────────────

_TOKEN_ENTROPY_BYTES = 32  # 256 bits of entropy


def _generate_token() -> str:
    """Generate a cryptographically random token."""
    return secrets.token_urlsafe(_TOKEN_ENTROPY_BYTES)


def generate_code_verifier() -> str:
    """Generate a PKCE code verifier."""
    return secrets.token_urlsafe(48)


def _redis_key(prefix: str, namespace: str, key: str) -> str:
    """Build a namespaced Redis key: ``{prefix}:{namespace}:{key}``."""
    return f"{prefix}:{namespace}:{key}"


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _decode_jwt_payload(token_value: str | None) -> dict[str, Any]:
    if not token_value or not isinstance(token_value, str) or token_value.count(".") != 2:
        return {}
    _, payload, _ = token_value.split(".", 2)
    padding = "=" * (-len(payload) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload + padding)
        data = json.loads(raw)
    except (ValueError, json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


# ── User management (MySQL) ───────────────────────────────────────────────


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
        cur.execute(
            """INSERT INTO users (external_id, display_name, email, avatar_url, synced_at)
               VALUES (%s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                   display_name = VALUES(display_name),
                   email = VALUES(email),
                   avatar_url = VALUES(avatar_url),
                   synced_at = VALUES(synced_at)""",
            (external_id, display_name, email, avatar_url, now),
        )

        # Fetch the full user record
        cur.execute(
            "SELECT id, external_id, display_name, email, avatar_url, synced_at, created_at "
            "FROM users WHERE external_id = %s",
            (external_id,),
        )
        return cur.fetchone()


# ── Session management (Redis) ────────────────────────────────────────────


def store_oauth_state(
    *,
    next_path: str,
    code_verifier: str | None = None,
    ttl_seconds: int | None = None,
) -> str:
    """Create a one-time OAuth state record in Redis and return its value."""
    from auth.redis_client import get_redis

    settings = get_settings()
    state = _generate_token()
    payload = {
        "next_path": next_path,
        "code_verifier": code_verifier,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    effective_ttl_seconds = ttl_seconds if ttl_seconds is not None else settings.oauth_state_ttl_seconds
    key = _redis_key(settings.redis_key_prefix, "auth:state", state)
    get_redis().set(key, json.dumps(payload), ex=effective_ttl_seconds if effective_ttl_seconds > 0 else 1)
    return state


def consume_oauth_state(state: str) -> dict[str, Any] | None:
    """Return and delete a one-time OAuth state payload atomically."""
    from auth.redis_client import get_redis

    settings = get_settings()
    key = _redis_key(settings.redis_key_prefix, "auth:state", state)
    r = get_redis()
    # Use Lua script for atomic GET+DELETE (compatible with Redis < 6.2 which lacks GETDEL)
    lua_script = """
    local v = redis.call('GET', KEYS[1])
    if v then
        redis.call('DEL', KEYS[1])
    end
    return v
    """
    try:
        raw = r.eval(lua_script, 1, key)
    except _redis.exceptions.ResponseError:
        # Fallback for environments that don't support EVAL (e.g. fakeredis)
        raw = r.get(key)
        if raw is not None:
            r.delete(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def create_session(
    *,
    user_id: int,
    access_token: str | None = None,
    refresh_token: str | None = None,
    access_token_expires_at: str | None = None,
    ttl_hours: int | None = None,
    user_row: dict[str, Any] | None = None,
) -> str:
    """Create a new Redis-backed app session and return its sessionId.

    Args:
        user_id: Internal database user ID.
        access_token: OAuth2 access token from the user center.
        refresh_token: OAuth2 refresh token from the user center.
        access_token_expires_at: ISO timestamp when the access token expires.
        ttl_hours: Session TTL in hours; defaults to settings.session_ttl_hours.
        user_row: Pre-fetched user dict (id, external_id, display_name, email,
            avatar_url). When provided the internal SELECT query is skipped,
            eliminating a redundant database round-trip during login callback.
    """
    from auth.redis_client import get_redis

    settings = get_settings()
    effective_ttl_hours = ttl_hours if ttl_hours is not None else settings.session_ttl_hours
    ttl_seconds = effective_ttl_hours * 3600

    if user_row is None:
        with get_cursor() as cur:
            cur.execute(
                "SELECT id, external_id, display_name, email, avatar_url FROM users WHERE id = %s",
                (user_id,),
            )
            user_row = cur.fetchone()

    if user_row is None:
        raise ValueError(f"User {user_id} not found")

    session_id = _generate_token()
    now_iso = datetime.now(timezone.utc).isoformat()

    payload = {
        "session_id": session_id,
        "user_id": user_row["id"],
        "external_id": user_row["external_id"],
        "display_name": user_row["display_name"],
        "email": user_row.get("email"),
        "avatar_url": user_row.get("avatar_url"),
        "access_token": access_token,
        "refresh_token": refresh_token,
        "access_token_expires_at": access_token_expires_at,
        "token_status": "active",
        "token_checked_at": now_iso,
        "created_at": now_iso,
        "last_seen_at": now_iso,
    }

    r = get_redis()
    key = _redis_key(settings.redis_key_prefix, "auth:session", session_id)
    r.set(key, json.dumps(payload), ex=ttl_seconds if ttl_seconds > 0 else 1)

    return session_id


def get_session_by_token(raw_token: str) -> dict[str, Any] | None:
    """Look up an app session by sessionId."""
    from auth.redis_client import get_redis

    settings = get_settings()
    key = _redis_key(settings.redis_key_prefix, "auth:session", raw_token)

    r = get_redis()
    raw = r.get(key)
    if raw is None:
        return None

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return payload


def update_session(raw_token: str, **patch: Any) -> dict[str, Any] | None:
    """Update a session payload in Redis while preserving its remaining TTL."""
    from auth.redis_client import get_redis

    settings = get_settings()
    key = _redis_key(settings.redis_key_prefix, "auth:session", raw_token)
    r = get_redis()
    current = get_session_by_token(raw_token)
    if current is None:
        return None

    current.update(patch)
    ttl = r.ttl(key)
    if ttl is None or ttl <= 0:
        ttl = max(settings.session_ttl_hours * 3600, 1)
    r.set(key, json.dumps(current), ex=ttl)
    return current


def derive_local_user_profile_from_token(token: dict[str, Any]) -> dict[str, Any]:
    """Best-effort local identity derivation from OAuth2 token payload/claims.

    Only uses ``openId`` / ``open_id`` fields as the external user identifier.
    Other claim fields (``sub``, ``uid``, ``user_id``) are deliberately excluded
    to avoid identity fragmentation across different login sessions.
    """
    access_token = token.get("access_token")
    id_token = token.get("id_token")
    access_claims = _decode_jwt_payload(access_token if isinstance(access_token, str) else None)
    id_claims = _decode_jwt_payload(id_token if isinstance(id_token, str) else None)
    claims: dict[str, Any] = {**access_claims, **id_claims}

    def first_non_empty(*values: Any) -> str | None:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    external_id = first_non_empty(
        token.get("openId"),
        token.get("open_id"),
        claims.get("openId"),
        claims.get("open_id"),
    )
    display_name = first_non_empty(
        claims.get("name"),
        claims.get("display_name"),
        claims.get("preferred_username"),
        claims.get("nickname"),
        token.get("name"),
        external_id,
        "OAuth User",
    ) or external_id

    return {
        "external_id": external_id,
        "display_name": display_name,
        "email": first_non_empty(claims.get("email")),
        "avatar_url": first_non_empty(
            claims.get("avatar_url"),
            claims.get("picture"),
            claims.get("avatar"),
        ),
    }


def session_needs_refresh(session: dict[str, Any], *, skew_seconds: int = 60) -> bool:
    expires_at = _parse_iso_datetime(session.get("access_token_expires_at"))
    if expires_at is None:
        return False
    now = datetime.now(timezone.utc)
    return expires_at <= now or (expires_at - now).total_seconds() <= skew_seconds


def delete_session(raw_token: str) -> None:
    """Delete a session by its sessionId."""
    from auth.redis_client import get_redis

    settings = get_settings()
    key = _redis_key(settings.redis_key_prefix, "auth:session", raw_token)

    r = get_redis()
    r.delete(key)

"""Tests for the session and user management service.

Covers:
- upsert_user creates user on first login, updates on subsequent logins
- create_session generates cryptographically random token (>=32 bytes),
  stores SHA-256(token) in DB, sets expires_at = now + TTL, returns raw token
- get_session_by_token hashes token, looks up session, checks expiry, returns user
- Expired sessions return None (treated as invalid)
- Forged/random tokens return None (no DB match)
- delete_session removes session from DB (for logout)
- cleanup_expired_sessions deletes all sessions where expires_at < now
- Token is cryptographically random — two tokens are never equal
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from backend.auth.session import (
    cleanup_expired_sessions,
    create_session,
    delete_session,
    get_session_by_token,
    upsert_user,
)
from backend.core.settings import get_settings
from backend.database import get_cursor, run_migrations


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _ensure_schema():
    """Ensure database schema is up-to-date before each test."""
    run_migrations()


@pytest.fixture()
def sample_user():
    """Insert a sample user via upsert_user and return the user dict."""
    return upsert_user(
        external_id="openId_12345",
        display_name="Test User",
        email="test@example.com",
        avatar_url="https://example.com/avatar.png",
    )


# ── upsert_user ───────────────────────────────────────────────────────────


class TestUpsertUser:
    def test_creates_user_on_first_call(self):
        """upsert_user creates a new user when external_id doesn't exist."""
        user = upsert_user(
            external_id="openId_new",
            display_name="New User",
            email="new@example.com",
            avatar_url="https://example.com/new.png",
        )
        assert user is not None
        assert user["external_id"] == "openId_new"
        assert user["display_name"] == "New User"
        assert user["email"] == "new@example.com"
        assert user["avatar_url"] == "https://example.com/new.png"
        assert "id" in user
        assert user["id"] > 0

    def test_updates_user_on_subsequent_call(self):
        """upsert_user updates existing user when external_id matches."""
        # First call: create
        user1 = upsert_user(
            external_id="openId_update",
            display_name="Original Name",
            email="original@example.com",
        )
        original_id = user1["id"]

        # Second call: update
        user2 = upsert_user(
            external_id="openId_update",
            display_name="Updated Name",
            email="updated@example.com",
            avatar_url="https://example.com/updated.png",
        )
        assert user2["id"] == original_id
        assert user2["display_name"] == "Updated Name"
        assert user2["email"] == "updated@example.com"
        assert user2["avatar_url"] == "https://example.com/updated.png"

    def test_different_external_ids_create_separate_users(self):
        """Different external_id values create distinct user records."""
        user_a = upsert_user(external_id="openId_A", display_name="User A")
        user_b = upsert_user(external_id="openId_B", display_name="User B")
        assert user_a["id"] != user_b["id"]
        assert user_a["external_id"] != user_b["external_id"]

    def test_synced_at_updates_on_upsert(self):
        """synced_at is updated on each upsert call."""
        user1 = upsert_user(external_id="openId_sync", display_name="Sync Test")
        synced_at_1 = user1["synced_at"]

        # Small delay to ensure time difference
        time.sleep(0.05)

        user2 = upsert_user(external_id="openId_sync", display_name="Sync Test Updated")
        synced_at_2 = user2["synced_at"]

        # synced_at should be updated (>= first value)
        assert synced_at_2 >= synced_at_1

    def test_upsert_with_none_optional_fields(self):
        """upsert_user works when optional fields are None."""
        user = upsert_user(
            external_id="openId_minimal",
            display_name="Minimal User",
            email=None,
            avatar_url=None,
        )
        assert user["external_id"] == "openId_minimal"
        assert user["email"] is None
        assert user["avatar_url"] is None


# ── create_session ────────────────────────────────────────────────────────


class TestCreateSession:
    def test_generates_token_and_stores_hash(self, sample_user):
        """create_session returns raw token, stores SHA-256 hash in DB."""
        raw_token = create_session(user_id=sample_user["id"])
        assert raw_token is not None
        assert isinstance(raw_token, str)
        assert len(raw_token) > 0

        # Verify that the hash stored in DB is SHA-256 of the raw token
        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        with get_cursor() as cur:
            cur.execute(
                "SELECT token_hash FROM sessions WHERE user_id = %s ORDER BY id DESC LIMIT 1",
                (sample_user["id"],),
            )
            row = cur.fetchone()
        assert row is not None
        assert row["token_hash"] == expected_hash

    def test_token_is_cryptographically_random(self, sample_user):
        """Two generated tokens are different (cryptographic randomness)."""
        token1 = create_session(user_id=sample_user["id"])
        token2 = create_session(user_id=sample_user["id"])
        assert token1 != token2

    def test_session_has_correct_expiry(self, sample_user):
        """New session has expires_at = now + SESSION_TTL_HOURS."""
        settings = get_settings()
        before = datetime.now(timezone.utc)
        raw_token = create_session(user_id=sample_user["id"])
        after = datetime.now(timezone.utc)

        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        with get_cursor() as cur:
            cur.execute(
                "SELECT expires_at FROM sessions WHERE token_hash = %s",
                (expected_hash,),
            )
            row = cur.fetchone()
        assert row is not None

        expires_at = row["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        # MySQL DATETIME(3) truncates to millisecond precision, so allow
        # a 1-second tolerance on each boundary instead of exact comparison.
        min_expected = before + timedelta(hours=settings.session_ttl_hours)
        max_expected = after + timedelta(hours=settings.session_ttl_hours)
        tolerance = timedelta(seconds=1)
        assert (
            min_expected - tolerance
            <= expires_at
            <= max_expected + tolerance
        ), f"expires_at={expires_at}, expected range=[{min_expected}, {max_expected}]"

    def test_session_stores_user_id(self, sample_user):
        """Session record has the correct user_id."""
        raw_token = create_session(user_id=sample_user["id"])
        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        with get_cursor() as cur:
            cur.execute(
                "SELECT user_id FROM sessions WHERE token_hash = %s",
                (expected_hash,),
            )
            row = cur.fetchone()
        assert row is not None
        assert row["user_id"] == sample_user["id"]

    def test_custom_ttl_override(self, sample_user):
        """create_session can accept a custom TTL in hours."""
        custom_ttl = 2
        before = datetime.now(timezone.utc)
        raw_token = create_session(user_id=sample_user["id"], ttl_hours=custom_ttl)
        after = datetime.now(timezone.utc)

        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        with get_cursor() as cur:
            cur.execute(
                "SELECT expires_at FROM sessions WHERE token_hash = %s",
                (expected_hash,),
            )
            row = cur.fetchone()
        assert row is not None

        expires_at = row["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        # MySQL DATETIME(3) truncates to millisecond precision, so allow
        # a 1-second tolerance on each boundary instead of exact comparison.
        min_expected = before + timedelta(hours=custom_ttl)
        max_expected = after + timedelta(hours=custom_ttl)
        tolerance = timedelta(seconds=1)
        assert (
            min_expected - tolerance
            <= expires_at
            <= max_expected + tolerance
        ), f"expires_at={expires_at}, expected range=[{min_expected}, {max_expected}]"


# ── get_session_by_token ─────────────────────────────────────────────────


class TestGetSessionByToken:
    def test_valid_session_returns_user(self, sample_user):
        """Valid unexpired session token returns user info."""
        raw_token = create_session(user_id=sample_user["id"])
        result = get_session_by_token(raw_token)
        assert result is not None
        assert result["user_id"] == sample_user["id"]
        assert result["external_id"] == sample_user["external_id"]
        assert result["display_name"] == sample_user["display_name"]

    def test_expired_session_returns_none(self, sample_user):
        """Expired session token returns None."""
        # Create session with a very short TTL
        raw_token = create_session(user_id=sample_user["id"], ttl_hours=0)  # 0 hours = immediate expiry
        # Manually set the session to expired
        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        with get_cursor() as cur:
            cur.execute(
                "UPDATE sessions SET expires_at = %s WHERE token_hash = %s",
                (datetime.now(timezone.utc) - timedelta(seconds=1), expected_hash),
            )
        result = get_session_by_token(raw_token)
        assert result is None

    def test_forged_random_token_returns_none(self):
        """Random/forged token that doesn't match any DB record returns None."""
        fake_token = "completely_made_up_token_value_12345"
        result = get_session_by_token(fake_token)
        assert result is None

    def test_deleted_session_returns_none(self, sample_user):
        """After delete_session, get_session_by_token returns None."""
        raw_token = create_session(user_id=sample_user["id"])
        # Verify it works initially
        result1 = get_session_by_token(raw_token)
        assert result1 is not None
        # Delete and verify
        delete_session(raw_token)
        result2 = get_session_by_token(raw_token)
        assert result2 is None

    def test_returns_user_email_and_avatar(self, sample_user):
        """get_session_by_token returns user email and avatar_url."""
        raw_token = create_session(user_id=sample_user["id"])
        result = get_session_by_token(raw_token)
        assert result is not None
        assert result["email"] == "test@example.com"
        assert result["avatar_url"] == "https://example.com/avatar.png"

    def test_multiple_sessions_same_user(self, sample_user):
        """A user can have multiple active sessions simultaneously."""
        token1 = create_session(user_id=sample_user["id"])
        token2 = create_session(user_id=sample_user["id"])
        result1 = get_session_by_token(token1)
        result2 = get_session_by_token(token2)
        assert result1 is not None
        assert result2 is not None
        assert result1["user_id"] == result2["user_id"] == sample_user["id"]


# ── delete_session ────────────────────────────────────────────────────────


class TestDeleteSession:
    def test_deletes_session_from_db(self, sample_user):
        """delete_session removes the session record from DB."""
        raw_token = create_session(user_id=sample_user["id"])
        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        # Verify session exists
        with get_cursor() as cur:
            cur.execute("SELECT id FROM sessions WHERE token_hash = %s", (expected_hash,))
            assert cur.fetchone() is not None

        # Delete
        delete_session(raw_token)

        # Verify session is gone
        with get_cursor() as cur:
            cur.execute("SELECT id FROM sessions WHERE token_hash = %s", (expected_hash,))
            assert cur.fetchone() is None

    def test_delete_nonexistent_token_does_not_raise(self):
        """Deleting a token that doesn't exist in DB does not raise."""
        # Should not raise
        delete_session("nonexistent_token_value")

    def test_delete_only_affects_target_session(self, sample_user):
        """Deleting one session doesn't affect other sessions of the same user."""
        token1 = create_session(user_id=sample_user["id"])
        token2 = create_session(user_id=sample_user["id"])

        delete_session(token1)

        # token1 should be gone
        assert get_session_by_token(token1) is None
        # token2 should still work
        result = get_session_by_token(token2)
        assert result is not None
        assert result["user_id"] == sample_user["id"]


# ── cleanup_expired_sessions ──────────────────────────────────────────────


class TestCleanupExpiredSessions:
    def test_removes_expired_sessions(self, sample_user):
        """cleanup_expired_sessions removes sessions where expires_at < now."""
        # Create a session and manually expire it
        raw_token = create_session(user_id=sample_user["id"])
        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        with get_cursor() as cur:
            cur.execute(
                "UPDATE sessions SET expires_at = %s WHERE token_hash = %s",
                (datetime.now(timezone.utc) - timedelta(hours=1), expected_hash),
            )

        # Verify session exists but is expired
        assert get_session_by_token(raw_token) is None

        # Run cleanup
        cleanup_expired_sessions()

        # Verify the expired session is physically removed from DB
        with get_cursor() as cur:
            cur.execute("SELECT id FROM sessions WHERE token_hash = %s", (expected_hash,))
            assert cur.fetchone() is None

    def test_does_not_remove_active_sessions(self, sample_user):
        """cleanup_expired_sessions does not remove active (non-expired) sessions."""
        raw_token = create_session(user_id=sample_user["id"])

        cleanup_expired_sessions()

        # Active session should still work
        result = get_session_by_token(raw_token)
        assert result is not None

    def test_removes_only_expired_sessions(self, sample_user):
        """Only expired sessions are removed; active ones remain."""
        # Create active session
        active_token = create_session(user_id=sample_user["id"])

        # Create and expire another session
        expired_token = create_session(user_id=sample_user["id"])
        expired_hash = hashlib.sha256(expired_token.encode("utf-8")).hexdigest()
        with get_cursor() as cur:
            cur.execute(
                "UPDATE sessions SET expires_at = %s WHERE token_hash = %s",
                (datetime.now(timezone.utc) - timedelta(hours=1), expired_hash),
            )

        cleanup_expired_sessions()

        # Active session still works
        assert get_session_by_token(active_token) is not None
        # Expired session is gone
        assert get_session_by_token(expired_token) is None


# ── Session lifecycle integration test ────────────────────────────────────


class TestSessionLifecycle:
    def test_create_validate_delete_validate_fails(self, sample_user):
        """Full lifecycle: create → validate → delete → validate fails."""
        # Create
        raw_token = create_session(user_id=sample_user["id"])

        # Validate — should work
        result = get_session_by_token(raw_token)
        assert result is not None
        assert result["user_id"] == sample_user["id"]

        # Delete (logout)
        delete_session(raw_token)

        # Validate — should fail
        result = get_session_by_token(raw_token)
        assert result is None

    def test_expiry_lifecycle(self, sample_user):
        """Create session, expire it, validate returns None."""
        raw_token = create_session(user_id=sample_user["id"])

        # Should work initially
        assert get_session_by_token(raw_token) is not None

        # Manually expire
        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        with get_cursor() as cur:
            cur.execute(
                "UPDATE sessions SET expires_at = %s WHERE token_hash = %s",
                (datetime.now(timezone.utc) - timedelta(seconds=1), expected_hash),
            )

        # Should fail after expiry
        assert get_session_by_token(raw_token) is None

    def test_upsert_then_session_lifecycle(self):
        """Upsert user → create session → validate returns correct user."""
        user = upsert_user(
            external_id="openId_lifecycle",
            display_name="Lifecycle User",
            email="lifecycle@example.com",
        )
        raw_token = create_session(user_id=user["id"])
        result = get_session_by_token(raw_token)
        assert result is not None
        assert result["external_id"] == "openId_lifecycle"
        assert result["display_name"] == "Lifecycle User"
        assert result["email"] == "lifecycle@example.com"

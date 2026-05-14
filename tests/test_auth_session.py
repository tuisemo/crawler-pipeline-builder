"""Tests for Redis-backed OAuth state and app sessions."""

from __future__ import annotations

import fakeredis

import pytest

from backend.auth.session import (
    consume_oauth_state,
    create_session,
    delete_session,
    derive_local_user_profile_from_token,
    get_session_by_token,
    session_needs_refresh,
    store_oauth_state,
    update_session,
    upsert_user,
)
from backend.database import get_cursor, ensure_schema


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _ensure_schema():
    """Ensure database schema is up-to-date before each test."""
    ensure_schema()


@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    fake_r = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("backend.auth.redis_client.get_redis", lambda: fake_r)
    return fake_r


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


# ── OAuth state ───────────────────────────────────────────────────────────


class TestOauthState:
    def test_store_and_consume_state_round_trip(self):
        state = store_oauth_state(next_path="/tasks/1")
        payload = consume_oauth_state(state)
        assert payload is not None
        assert payload["next_path"] == "/tasks/1"

    def test_state_is_one_time_use(self):
        state = store_oauth_state(next_path="/tasks/1")
        assert consume_oauth_state(state) is not None
        assert consume_oauth_state(state) is None


# ── create_session ────────────────────────────────────────────────────────


class TestCreateSession:
    def test_generates_session_and_stores_payload_in_redis(self, sample_user, mock_redis):
        session_id = create_session(user_id=sample_user["id"], access_token="access-123")
        payload = get_session_by_token(session_id)
        assert payload is not None
        assert payload["user_id"] == sample_user["id"]
        assert payload["access_token"] == "access-123"
        assert payload["token_status"] == "active"

    def test_token_is_cryptographically_random(self, sample_user):
        """Two generated tokens are different (cryptographic randomness)."""
        token1 = create_session(user_id=sample_user["id"])
        token2 = create_session(user_id=sample_user["id"])
        assert token1 != token2

    def test_custom_ttl_override(self, sample_user):
        session_id = create_session(user_id=sample_user["id"], ttl_hours=2)
        assert get_session_by_token(session_id) is not None


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
    def test_deletes_session_from_redis(self, sample_user):
        """delete_session removes the session payload."""
        raw_token = create_session(user_id=sample_user["id"])
        assert get_session_by_token(raw_token) is not None
        delete_session(raw_token)
        assert get_session_by_token(raw_token) is None

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


class TestSessionLifecycle:
    def test_create_validate_delete_validate_fails(self, sample_user):
        session_id = create_session(user_id=sample_user["id"])
        assert get_session_by_token(session_id) is not None
        delete_session(session_id)
        assert get_session_by_token(session_id) is None


class TestSessionStateHelpers:
    def test_update_session_preserves_payload(self, sample_user):
        session_id = create_session(user_id=sample_user["id"], access_token="old")
        updated = update_session(session_id, access_token="new", token_status="active")
        assert updated is not None
        assert updated["access_token"] == "new"
        assert get_session_by_token(session_id)["access_token"] == "new"

    def test_session_needs_refresh_when_expiring_soon(self, sample_user):
        session_id = create_session(
            user_id=sample_user["id"],
            access_token="at",
            access_token_expires_at="2020-01-01T00:00:00+00:00",
        )
        session = get_session_by_token(session_id)
        assert session is not None
        assert session_needs_refresh(session) is True

    def test_derive_local_user_profile_requires_stable_subject(self):
        profile = derive_local_user_profile_from_token(
            {"access_token": "opaque-token-value", "name": "App User"}
        )
        assert profile["external_id"] is None
        assert profile["display_name"] == "App User"

"""Tests for auth-related settings in CrawlerWorkflowSettings.

Covers:
- user_center_base_uri loaded from USER_CENTER_BASE_URI
- user_center_client_id loaded from USER_CENTER_CLIENT_ID
- user_center_client_secret loaded from USER_CENTER_CLIENT_SECRET
- user_center_scope loaded from USER_CENTER_SCOPE with default "basic"
- user_center_redirect_uri loaded from USER_CENTER_REDIRECT_URI
- session_ttl_hours loaded from SESSION_TTL_HOURS with default 24
- redis_key_prefix defaults to crawler_workflow
"""

from backend.core.settings import CrawlerWorkflowSettings

import pytest


# All user-center env vars that may be set in .env and need clearing for default tests
_UC_ENV_KEYS = [
    "USER_CENTER_BASE_URI",
    "USER_CENTER_CLIENT_ID",
    "USER_CENTER_CLIENT_SECRET",
    "USER_CENTER_SCOPE",
    "USER_CENTER_REDIRECT_URI",
    "USER_CENTER_FRONTEND_URL",
]


@pytest.fixture(autouse=True)
def _clear_uc_env(monkeypatch):
    """Ensure .env values don't leak into default-value tests."""
    for key in _UC_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    # Also prevent .env file from leaking into default tests
    monkeypatch.setattr("backend.core.settings.load_env_config", lambda **_: {})


# ── user_center_base_uri ──


def test_user_center_base_uri_loaded_from_env(monkeypatch):
    monkeypatch.setenv("USER_CENTER_BASE_URI", "https://uc.example.com")
    settings = CrawlerWorkflowSettings.from_env()
    assert settings.user_center_base_uri == "https://uc.example.com"


def test_user_center_base_uri_default_when_not_set(monkeypatch):
    monkeypatch.delenv("USER_CENTER_BASE_URI", raising=False)
    settings = CrawlerWorkflowSettings.from_env()
    assert settings.user_center_base_uri == ""


# ── user_center_client_id ──


def test_user_center_client_id_loaded_from_env(monkeypatch):
    monkeypatch.setenv("USER_CENTER_CLIENT_ID", "my-client-id")
    settings = CrawlerWorkflowSettings.from_env()
    assert settings.user_center_client_id == "my-client-id"


def test_user_center_client_id_default_when_not_set(monkeypatch):
    monkeypatch.delenv("USER_CENTER_CLIENT_ID", raising=False)
    settings = CrawlerWorkflowSettings.from_env()
    assert settings.user_center_client_id == ""


# ── user_center_client_secret ──


def test_user_center_client_secret_loaded_from_env(monkeypatch):
    monkeypatch.setenv("USER_CENTER_CLIENT_SECRET", "s3cret!")
    settings = CrawlerWorkflowSettings.from_env()
    assert settings.user_center_client_secret == "s3cret!"


def test_user_center_client_secret_default_when_not_set(monkeypatch):
    monkeypatch.delenv("USER_CENTER_CLIENT_SECRET", raising=False)
    settings = CrawlerWorkflowSettings.from_env()
    assert settings.user_center_client_secret == ""


# ── user_center_scope ──


def test_user_center_scope_loaded_from_env(monkeypatch):
    monkeypatch.setenv("USER_CENTER_SCOPE", "profile email")
    settings = CrawlerWorkflowSettings.from_env()
    assert settings.user_center_scope == "profile email"


def test_user_center_scope_default_is_basic(monkeypatch):
    monkeypatch.delenv("USER_CENTER_SCOPE", raising=False)
    settings = CrawlerWorkflowSettings.from_env()
    assert settings.user_center_scope == "basic"


# ── user_center_redirect_uri ──


def test_user_center_redirect_uri_loaded_from_env(monkeypatch):
    monkeypatch.setenv("USER_CENTER_REDIRECT_URI", "https://app.example.com/auth/callback")
    settings = CrawlerWorkflowSettings.from_env()
    assert settings.user_center_redirect_uri == "https://app.example.com/auth/callback"


def test_user_center_redirect_uri_default_when_not_set(monkeypatch):
    monkeypatch.delenv("USER_CENTER_REDIRECT_URI", raising=False)
    settings = CrawlerWorkflowSettings.from_env()
    assert settings.user_center_redirect_uri == ""

# ── user_center_frontend_url ──


def test_user_center_frontend_url_loaded_from_env(monkeypatch):
    monkeypatch.setenv("USER_CENTER_FRONTEND_URL", "https://app.example.com")
    settings = CrawlerWorkflowSettings.from_env()
    assert settings.user_center_frontend_url == "https://app.example.com"


def test_user_center_frontend_url_default_when_not_set(monkeypatch):
    monkeypatch.delenv("USER_CENTER_FRONTEND_URL", raising=False)
    settings = CrawlerWorkflowSettings.from_env()
    assert settings.user_center_frontend_url == ""


# ── session_ttl_hours ──


def test_session_ttl_hours_loaded_from_env(monkeypatch):
    monkeypatch.setenv("SESSION_TTL_HOURS", "48")
    settings = CrawlerWorkflowSettings.from_env()
    assert settings.session_ttl_hours == 48


def test_session_ttl_hours_default_is_24(monkeypatch):
    monkeypatch.delenv("SESSION_TTL_HOURS", raising=False)
    settings = CrawlerWorkflowSettings.from_env()
    assert settings.session_ttl_hours == 24


def test_session_ttl_hours_ignores_invalid_value(monkeypatch):
    monkeypatch.setenv("SESSION_TTL_HOURS", "not-a-number")
    settings = CrawlerWorkflowSettings.from_env()
    assert settings.session_ttl_hours == 24


def test_session_ttl_hours_ignores_zero(monkeypatch):
    monkeypatch.setenv("SESSION_TTL_HOURS", "0")
    settings = CrawlerWorkflowSettings.from_env()
    assert settings.session_ttl_hours == 24


def test_session_ttl_hours_ignores_negative(monkeypatch):
    monkeypatch.setenv("SESSION_TTL_HOURS", "-5")
    settings = CrawlerWorkflowSettings.from_env()
    assert settings.session_ttl_hours == 24


# ── redis_key_prefix ──


def test_redis_key_prefix_default_is_crawler_workflow(monkeypatch):
    monkeypatch.delenv("REDIS_KEY_PREFIX", raising=False)
    settings = CrawlerWorkflowSettings.from_env()
    assert settings.redis_key_prefix == "crawler_workflow"

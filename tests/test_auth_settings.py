"""Tests for auth-related settings in CrawlerWorkflowSettings.

Covers:
- user_center_base_uri loaded from USER_CENTER_BASE_URI
- user_center_client_id loaded from USER_CENTER_CLIENT_ID
- user_center_client_secret loaded from USER_CENTER_CLIENT_SECRET
- user_center_scope loaded from USER_CENTER_SCOPE with default "basic"
- user_center_redirect_uri loaded from USER_CENTER_REDIRECT_URI
- session_ttl_hours loaded from SESSION_TTL_HOURS with default 24
- session_cookie_name loaded from SESSION_COOKIE_NAME with default "session_token"
"""

from backend.core.settings import CrawlerWorkflowSettings


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
    monkeypatch.setenv("USER_CENTER_REDIRECT_URI", "https://app.example.com/api/auth/callback")
    settings = CrawlerWorkflowSettings.from_env()
    assert settings.user_center_redirect_uri == "https://app.example.com/api/auth/callback"


def test_user_center_redirect_uri_default_when_not_set(monkeypatch):
    monkeypatch.delenv("USER_CENTER_REDIRECT_URI", raising=False)
    settings = CrawlerWorkflowSettings.from_env()
    assert settings.user_center_redirect_uri == ""


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


# ── session_cookie_name ──


def test_session_cookie_name_loaded_from_env(monkeypatch):
    monkeypatch.setenv("SESSION_COOKIE_NAME", "my_session")
    settings = CrawlerWorkflowSettings.from_env()
    assert settings.session_cookie_name == "my_session"


def test_session_cookie_name_default_is_session_token(monkeypatch):
    monkeypatch.delenv("SESSION_COOKIE_NAME", raising=False)
    settings = CrawlerWorkflowSettings.from_env()
    assert settings.session_cookie_name == "session_token"

"""Tests for the user-center Authlib helper client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from auth.user_center_client import (
    UserCenterError,
    build_authorize_url,
    exchange_code_for_token,
    exchange_code_for_user,
)


def test_build_authorize_url_delegates_to_authlib(monkeypatch):
    fake_client = MagicMock()
    fake_client.create_authorization_url.return_value = ("https://uc.example.com/oauth/authorize?state=abc", "abc")
    monkeypatch.setattr("auth.user_center_client.create_oauth_client", lambda redirect_uri: fake_client)
    monkeypatch.setattr("auth.user_center_client.get_authorize_url", lambda: "https://uc.example.com/oauth/authorize")

    url = build_authorize_url(redirect_uri="https://app.example.com/auth/callback", state="abc")

    assert url == "https://uc.example.com/oauth/authorize?state=abc"
    fake_client.create_authorization_url.assert_called_once()


def _mock_async_client(response_json: dict):
    """Create a mock httpx.AsyncClient that returns the given JSON."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = response_json

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.post = AsyncMock(return_value=mock_resp)

    mock_cls = MagicMock(return_value=mock_client)
    return mock_cls


@pytest.mark.anyio
async def test_exchange_code_for_token_returns_access_token(monkeypatch):
    fake_client = MagicMock()
    fake_client.fetch_token = AsyncMock(return_value={"access_token": "at"})
    fake_client.aclose = AsyncMock()
    monkeypatch.setattr(
        "auth.user_center_client.create_oauth_client",
        lambda redirect_uri: fake_client,
    )
    monkeypatch.setattr(
        "auth.user_center_client.get_access_token_url",
        lambda: "https://uc.example.com/oauth/token",
    )

    result = await exchange_code_for_token(
        code="auth-code-123",
        redirect_uri="https://app.example.com/auth/callback",
    )

    assert result["access_token"] == "at"
    fake_client.fetch_token.assert_awaited_once()
    fake_client.aclose.assert_awaited_once()


@pytest.mark.anyio
async def test_exchange_code_for_user_gets_openid_from_user_get(monkeypatch):
    """exchange_code_for_user uses token endpoint then /user/get."""
    monkeypatch.setattr(
        "auth.user_center_client.exchange_code_for_token",
        AsyncMock(return_value={"access_token": "fake-access-token"}),
    )
    mock_cls = _mock_async_client({
        "openId": "cb067d55-05ad-487a-a33c-e99aed87a4e3",
        "displayName": "测试用户",
    })

    with patch("auth.user_center_client.httpx.AsyncClient", mock_cls):
        result = await exchange_code_for_user(code="auth-code-123", redirect_uri="https://app.example.com/auth/callback")

    assert result["openId"] == "cb067d55-05ad-487a-a33c-e99aed87a4e3"
    assert result["displayName"] == "测试用户"
    assert result["access_token"] == "fake-access-token"


@pytest.mark.anyio
async def test_exchange_code_for_user_uses_open_id_field(monkeypatch):
    """Also supports open_id (snake_case) from /user/get response."""
    monkeypatch.setattr(
        "auth.user_center_client.exchange_code_for_token",
        AsyncMock(return_value={"access_token": "at"}),
    )
    mock_cls = _mock_async_client({
        "open_id": "uuid-from-snake-case",
        "name": "User",
    })

    with patch("auth.user_center_client.httpx.AsyncClient", mock_cls):
        result = await exchange_code_for_user(code="auth-code-123", redirect_uri="https://app.example.com/auth/callback")

    assert result["openId"] == "uuid-from-snake-case"


@pytest.mark.anyio
async def test_exchange_code_for_user_raises_on_error_response(monkeypatch):
    """Raises UserCenterError when /user/get returns respCode error."""
    monkeypatch.setattr(
        "auth.user_center_client.exchange_code_for_token",
        AsyncMock(return_value={"access_token": "at"}),
    )
    mock_cls = _mock_async_client({
        "respCode": "E001",
        "respMsg": "无法找到登录方式的实现类",
    })

    with patch("auth.user_center_client.httpx.AsyncClient", mock_cls):
        with pytest.raises(UserCenterError, match="无法找到登录方式的实现类"):
            await exchange_code_for_user(code="auth-code-123", redirect_uri="https://app.example.com/auth/callback")


@pytest.mark.anyio
async def test_exchange_code_for_user_raises_on_http_error(monkeypatch):
    """Raises UserCenterError when /user/get throws an HTTP error."""
    monkeypatch.setattr(
        "auth.user_center_client.exchange_code_for_token",
        AsyncMock(return_value={"access_token": "at"}),
    )
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection failed"))
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection failed"))

    mock_cls = MagicMock(return_value=mock_client)

    with patch("auth.user_center_client.httpx.AsyncClient", mock_cls):
        with pytest.raises(UserCenterError, match="Failed to fetch user details from user center"):
            await exchange_code_for_user(code="auth-code-123", redirect_uri="https://app.example.com/auth/callback")


@pytest.mark.anyio
async def test_exchange_code_for_user_raises_when_no_openId(monkeypatch):
    """Raises UserCenterError when /user/get response has no openId."""
    monkeypatch.setattr(
        "auth.user_center_client.exchange_code_for_token",
        AsyncMock(return_value={"access_token": "at"}),
    )
    mock_cls = _mock_async_client({
        "displayName": "No OpenId User",
    })

    with patch("auth.user_center_client.httpx.AsyncClient", mock_cls):
        with pytest.raises(UserCenterError, match="did not return openId"):
            await exchange_code_for_user(code="auth-code-123", redirect_uri="https://app.example.com/auth/callback")

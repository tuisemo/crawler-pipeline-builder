"""OAuth client helpers powered by Authlib."""

from __future__ import annotations

from authlib.integrations.httpx_client import AsyncOAuth2Client

from core.settings import get_settings


def get_authorize_url() -> str:
    settings = get_settings()
    return f"{settings.user_center_base_uri.rstrip('/')}/oauth/authorize"


def get_access_token_url() -> str:
    settings = get_settings()
    return f"{settings.user_center_base_uri.rstrip('/')}/oauth/token"


def get_user_details_url() -> str:
    settings = get_settings()
    return f"{settings.user_center_base_uri.rstrip('/')}/user/get"


def create_oauth_client(*, redirect_uri: str | None = None) -> AsyncOAuth2Client:
    settings = get_settings()
    return AsyncOAuth2Client(
        client_id=settings.user_center_client_id,
        client_secret=settings.user_center_client_secret,
        scope=settings.user_center_scope,
        redirect_uri=redirect_uri,
        token_endpoint_auth_method="client_secret_post",
    )

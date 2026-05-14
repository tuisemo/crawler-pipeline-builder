"""Redis connection management.

Provides a lazily initialised Redis client shared across the process.
Supports both standalone (``REDIS_URL``) and Sentinel mode
(``REDIS_SENTINEL_NODES``). When Sentinel is configured, it takes
precedence over ``REDIS_URL``.

Usage::

    from backend.auth.redis_client import get_redis

    r = get_redis()
    r.set("key", "value", ex=60)
"""

from __future__ import annotations

import redis as _redis

from backend.core.settings import get_settings

_client: _redis.Redis | None = None


def _parse_sentinel_nodes(raw: str) -> list[tuple[str, int]]:
    """Parse ``host:port`` pairs separated by commas."""
    nodes: list[tuple[str, int]] = []
    for part in raw.split(","):
        part = part.strip()
        if ":" not in part:
            continue
        host, port_str = part.rsplit(":", 1)
        try:
            nodes.append((host.strip(), int(port_str.strip())))
        except ValueError:
            continue
    return nodes


def get_redis() -> _redis.Redis:
    """Return the module-level Redis client, initialising it on first call.

    If ``REDIS_SENTINEL_NODES`` is set, creates a Sentinel-backed client.
    Otherwise falls back to ``REDIS_URL`` standalone mode.

    The client is configured with ``decode_responses=True`` so all
    returned values are ``str`` rather than ``bytes``.
    """
    global _client
    if _client is not None:
        return _client

    settings = get_settings()

    sentinel_nodes_raw = settings.redis_sentinel_nodes
    if sentinel_nodes_raw:
        from redis.sentinel import Sentinel

        nodes = _parse_sentinel_nodes(sentinel_nodes_raw)
        if not nodes:
            raise ValueError(
                f"REDIS_SENTINEL_NODES is set but could not be parsed: {sentinel_nodes_raw!r}"
            )

        sentinel_kwargs: dict = {"socket_connect_timeout": 5}
        if settings.redis_sentinel_password:
            sentinel_kwargs["password"] = settings.redis_sentinel_password

        sentinel = Sentinel(nodes, sentinel_kwargs=sentinel_kwargs)

        master_kwargs: dict = {
            "db": settings.redis_db,
            "decode_responses": True,
        }
        if settings.redis_password:
            master_kwargs["password"] = settings.redis_password

        _client = sentinel.master_for(
            settings.redis_sentinel_master,
            **master_kwargs,
        )
    else:
        _client = _redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )

    return _client


def close_redis() -> None:
    """Close the Redis client (call on application shutdown)."""
    global _client
    if _client is not None:
        _client.close()
        _client = None

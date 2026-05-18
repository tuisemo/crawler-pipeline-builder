"""Consistent API response envelopes."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse
from pydantic import BaseModel


ENVELOPE_KEYS = {"success", "error_code", "error", "data", "warnings", "meta"}


def _to_plain_payload(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, BaseModel):
        return payload.model_dump(exclude_none=True)
    if isinstance(payload, dict):
        return payload
    return {"value": payload}


def build_api_envelope(
    payload: Any = None,
    *,
    success: bool | None = None,
    error_code: str | None = None,
    error: str | None = None,
    warnings: list[Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a transport envelope around a service payload."""
    body = _to_plain_payload(payload)
    resolved_success = bool(body.get("success", True)) if success is None else success
    resolved_error = error if error is not None else body.get("error")
    resolved_error_code = error_code if error_code is not None else body.get("error_code")
    resolved_warnings = warnings if warnings is not None else body.get("warnings", [])
    data = {key: value for key, value in body.items() if key not in ENVELOPE_KEYS}

    return {
        "success": resolved_success,
        "error_code": resolved_error_code,
        "error": resolved_error,
        "data": data,
        "warnings": resolved_warnings or [],
        "meta": meta or {},
    }


def api_response(
    payload: Any = None,
    *,
    status_code: int = 200,
    success: bool | None = None,
    error_code: str | None = None,
    error: str | None = None,
    warnings: list[Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=build_api_envelope(
            payload,
            success=success,
            error_code=error_code,
            error=error,
            warnings=warnings,
            meta=meta,
        ),
    )

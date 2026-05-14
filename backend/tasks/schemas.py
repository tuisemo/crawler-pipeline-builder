"""Pydantic models for task CRUD API."""

from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------

VALID_ASSET_TYPES = frozenset([
    "workflow_graph",
    "compile_plan",
    "list_script",
    "prompt",
    "detail_batch_config",
    "detail_batch_script",
])

VALID_TASK_STATUSES = frozenset(["draft", "active", "archived"])

_URL_PATTERN = re.compile(r"^https?://\S+$", re.IGNORECASE)


# ----------------------------------------------------------------------
# Asset response models
# ----------------------------------------------------------------------


class TaskAssetResponse(BaseModel):
    """Asset metadata returned with task detail."""

    asset_type: str
    version: int
    created_at: str


# ----------------------------------------------------------------------
# Task request models
# ----------------------------------------------------------------------


class CreateTaskRequest(BaseModel):
    """Request body for creating a new task."""

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    target_url: Optional[str] = None

    @field_validator("target_url")
    @classmethod
    def validate_target_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not _URL_PATTERN.match(v):
            raise ValueError(f"Invalid URL format: {v!r}. Must start with http:// or https://")
        return v


class UpdateTaskRequest(BaseModel):
    """Request body for partially updating a task."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    target_url: Optional[str] = None
    status: Optional[str] = None

    @field_validator("target_url")
    @classmethod
    def validate_target_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not _URL_PATTERN.match(v):
            raise ValueError(f"Invalid URL format: {v!r}. Must start with http:// or https://")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_TASK_STATUSES:
            raise ValueError(
                f"Invalid status: {v!r}. Must be one of {sorted(VALID_TASK_STATUSES)}"
            )
        return v


# ----------------------------------------------------------------------
# Task response models
# ----------------------------------------------------------------------


class TaskResponse(BaseModel):
    """Task object returned by list and create endpoints."""

    id: int
    name: str
    description: Optional[str] = None
    target_url: Optional[str] = None
    status: str
    created_at: str
    updated_at: str


class TaskDetailResponse(BaseModel):
    """Task detail response including asset metadata."""

    task: TaskResponse
    assets: list[TaskAssetResponse]


class TaskListResponse(BaseModel):
    """Paginated task list response."""

    items: list[TaskResponse]
    total: int
    page: int
    page_size: int


# ----------------------------------------------------------------------
# Asset request/response models (for assets endpoints)
# ----------------------------------------------------------------------


class SaveAssetRequest(BaseModel):
    """Request body for saving assets to a task."""

    assets: dict[str, Any] = Field(..., description="Mapping of asset_type to content")


class SaveAssetResponse(BaseModel):
    """Response after saving assets."""

    saved_count: int
    versions: dict[str, int]


class GetAssetResponse(BaseModel):
    """Single asset content response."""

    content: Optional[str]
    asset_type: str
    version: int
    created_at: Optional[str] = None

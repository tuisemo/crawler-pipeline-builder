"""Pydantic models for task CRUD API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ----------------------------------------------------------------------
# Asset type enum
# ----------------------------------------------------------------------

VALID_ASSET_TYPES = frozenset([
    "workflow_graph",
    "compile_plan",
    "list_script",
    "prompt",
    "detail_batch_config",
    "detail_batch_script",
])


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


class UpdateTaskRequest(BaseModel):
    """Request body for partially updating a task."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    target_url: Optional[str] = None
    status: Optional[str] = None


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
    created_at: str

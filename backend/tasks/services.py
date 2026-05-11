"""Business logic for task CRUD operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from backend.database.db import get_cursor
from backend.tasks.schemas import (
    VALID_ASSET_TYPES,
    CreateTaskRequest,
    SaveAssetResponse,
    TaskAssetResponse,
    TaskDetailResponse,
    TaskListResponse,
    TaskResponse,
    UpdateTaskRequest,
)


def _now_iso() -> str:
    """Return current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _task_row_to_response(row: tuple, assets: list[TaskAssetResponse] | None = None) -> dict[str, Any]:
    """Convert a database row to a response dict."""
    return {
        "id": row[0],
        "name": row[1],
        "description": row[2],
        "target_url": row[3],
        "status": row[4],
        "created_at": row[5],
        "updated_at": row[6],
    }


# ----------------------------------------------------------------------
# Task CRUD services
# ----------------------------------------------------------------------


def create_task(request: CreateTaskRequest) -> TaskResponse:
    """Create a new task with draft status."""
    now = _now_iso()
    with get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO tasks (name, description, target_url, status, created_at, updated_at)
            VALUES (?, ?, ?, 'draft', ?, ?)
            """,
            (request.name, request.description, request.target_url, now, now),
        )
        task_id = cursor.lastrowid
        cursor.execute(
            "SELECT id, name, description, target_url, status, created_at, updated_at FROM tasks WHERE id = ?",
            (task_id,),
        )
        row = cursor.fetchone()
    return TaskResponse(**_task_row_to_response(row))


def list_tasks(page: int = 1, page_size: int = 20, include_archived: bool = False) -> TaskListResponse:
    """List tasks with pagination, excluding archived by default."""
    offset = (page - 1) * page_size

    with get_cursor() as cursor:
        # Count total
        if include_archived:
            cursor.execute("SELECT COUNT(*) FROM tasks")
        else:
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE status != 'archived'")
        total = cursor.fetchone()[0]

        # Fetch page
        if include_archived:
            cursor.execute(
                """
                SELECT id, name, description, target_url, status, created_at, updated_at
                FROM tasks
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (page_size, offset),
            )
        else:
            cursor.execute(
                """
                SELECT id, name, description, target_url, status, created_at, updated_at
                FROM tasks
                WHERE status != 'archived'
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (page_size, offset),
            )
        rows = cursor.fetchall()

    items = [TaskResponse(**_task_row_to_response(row)) for row in rows]
    return TaskListResponse(items=items, total=total, page=page, page_size=page_size)


def get_task(task_id: int) -> TaskDetailResponse:
    """Get task detail including asset metadata."""
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT id, name, description, target_url, status, created_at, updated_at FROM tasks WHERE id = ?",
            (task_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Task {task_id} not found")

        cursor.execute(
            "SELECT asset_type, version, created_at FROM task_assets WHERE task_id = ? ORDER BY created_at DESC",
            (task_id,),
        )
        asset_rows = cursor.fetchall()

    task = TaskResponse(**_task_row_to_response(row))
    assets = [TaskAssetResponse(asset_type=r[0], version=r[1], created_at=r[2]) for r in asset_rows]
    return TaskDetailResponse(task=task, assets=assets)


def update_task(task_id: int, request: UpdateTaskRequest) -> TaskResponse:
    """Partially update a task (only provided fields are updated)."""
    updates: list[str] = []
    params: list[Any] = []

    if request.name is not None:
        updates.append("name = ?")
        params.append(request.name)
    if request.description is not None:
        updates.append("description = ?")
        params.append(request.description)
    if request.target_url is not None:
        updates.append("target_url = ?")
        params.append(request.target_url)
    if request.status is not None:
        updates.append("status = ?")
        params.append(request.status)

    if not updates:
        # No fields to update, just return current task
        return get_task(task_id).task

    updates.append("updated_at = ?")
    params.append(_now_iso())
    params.append(task_id)

    with get_cursor() as cursor:
        cursor.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params)
        cursor.execute(
            "SELECT id, name, description, target_url, status, created_at, updated_at FROM tasks WHERE id = ?",
            (task_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Task {task_id} not found")

    return TaskResponse(**_task_row_to_response(row))


def delete_task(task_id: int) -> TaskResponse:
    """Soft delete a task by setting status to 'archived'."""
    now = _now_iso()
    with get_cursor() as cursor:
        cursor.execute("UPDATE tasks SET status = 'archived', updated_at = ? WHERE id = ?", (now, task_id))
        cursor.execute(
            "SELECT id, name, description, target_url, status, created_at, updated_at FROM tasks WHERE id = ?",
            (task_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Task {task_id} not found")

    return TaskResponse(**_task_row_to_response(row))


# ----------------------------------------------------------------------
# Asset services
# ----------------------------------------------------------------------


def save_assets(task_id: int, assets: dict[str, Any]) -> SaveAssetResponse:
    """Save or update assets for a task. Invalid asset types raise ValueError."""
    for asset_type in assets.keys():
        if asset_type not in VALID_ASSET_TYPES:
            raise ValueError(f"Invalid asset type: {asset_type}. Must be one of {sorted(VALID_ASSET_TYPES)}")

    now = _now_iso()
    versions: dict[str, int] = {}

    with get_cursor() as cursor:
        # Verify task exists
        cursor.execute("SELECT id FROM tasks WHERE id = ?", (task_id,))
        if cursor.fetchone() is None:
            raise ValueError(f"Task {task_id} not found")

        for asset_type, content in assets.items():
            # Get current version or 0
            cursor.execute(
                "SELECT version FROM task_assets WHERE task_id = ? AND asset_type = ? ORDER BY version DESC LIMIT 1",
                (task_id, asset_type),
            )
            row = cursor.fetchone()
            new_version = (row[0] if row else 0) + 1

            # Insert new asset version
            cursor.execute(
                "INSERT INTO task_assets (task_id, asset_type, content, version, created_at) VALUES (?, ?, ?, ?, ?)",
                (task_id, asset_type, content, new_version, now),
            )
            versions[asset_type] = new_version

    return SaveAssetResponse(saved_count=len(assets), versions=versions)


def get_asset(task_id: int, asset_type: str) -> dict[str, Any]:
    """Get the latest version of a specific asset type for a task."""
    if asset_type not in VALID_ASSET_TYPES:
        raise ValueError(f"Invalid asset type: {asset_type}. Must be one of {sorted(VALID_ASSET_TYPES)}")

    with get_cursor() as cursor:
        # Verify task exists
        cursor.execute("SELECT id FROM tasks WHERE id = ?", (task_id,))
        if cursor.fetchone() is None:
            raise ValueError(f"Task {task_id} not found")

        cursor.execute(
            "SELECT content, asset_type, version, created_at FROM task_assets WHERE task_id = ? AND asset_type = ? ORDER BY version DESC LIMIT 1",
            (task_id, asset_type),
        )
        row = cursor.fetchone()

    if row is None:
        return {"content": None, "asset_type": asset_type, "version": 0, "created_at": None}

    return {
        "content": row[0],
        "asset_type": row[1],
        "version": row[2],
        "created_at": row[3],
    }

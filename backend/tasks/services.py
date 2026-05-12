"""Business logic for task CRUD operations.

All functions require an ``owner_user_id`` parameter (derived from the
authenticated user).  The owner constraint is enforced at the service
layer so that non-owner access raises ``TaskNotFoundError`` (which
maps to 404 in the route layer — intentionally NOT 403, to prevent
task-ID enumeration).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

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


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TaskNotFoundError(Exception):
    """Raised when a task is not found OR the user does not own it.

    Both conditions produce the same error to avoid task-ID enumeration.
    """


def _check_task_owner(cursor, task_id: int, owner_user_id: int) -> dict:
    """Fetch a task row, raising TaskNotFoundError if not found or not owned.

    Both conditions produce the same error to avoid task-ID enumeration.

    Returns the task row dict on success.
    """
    cursor.execute(
        "SELECT id, name, description, target_url, status, created_at, updated_at, owner_user_id "
        "FROM tasks WHERE id = %s",
        (task_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise TaskNotFoundError(f"Task {task_id} not found")
    if row["owner_user_id"] != owner_user_id:
        raise TaskNotFoundError(f"Task {task_id} not found")
    return row


# -- Task CRUD ---------------------------------------------------------------


def create_task(request: CreateTaskRequest, owner_user_id: int) -> TaskResponse:
    now = _now()
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO tasks (owner_user_id, name, description, target_url, status, created_at, updated_at)
               VALUES (%s, %s, %s, %s, 'draft', %s, %s)""",
            (owner_user_id, request.name, request.description, request.target_url, now, now),
        )
        task_id = cursor.lastrowid
        cursor.execute(
            """SELECT id, name, description, target_url, status, created_at, updated_at
               FROM tasks WHERE id = %s""",
            (task_id,),
        )
        row = cursor.fetchone()
    return _row_to_task_response(row)


def list_tasks(
    owner_user_id: int,
    page: int = 1,
    page_size: int = 20,
    include_archived: bool = False,
) -> TaskListResponse:
    offset = (page - 1) * page_size
    with get_cursor() as cursor:
        if include_archived:
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM tasks WHERE owner_user_id = %s",
                (owner_user_id,),
            )
        else:
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM tasks WHERE owner_user_id = %s AND status != 'archived'",
                (owner_user_id,),
            )
        total = cursor.fetchone()["cnt"]

        if include_archived:
            where = "WHERE owner_user_id = %s "
        else:
            where = "WHERE owner_user_id = %s AND status != 'archived' "

        cursor.execute(
            f"""SELECT id, name, description, target_url, status, created_at, updated_at
                FROM tasks {where}
                ORDER BY created_at DESC LIMIT %s OFFSET %s""",
            (owner_user_id, page_size, offset),
        )
        rows = cursor.fetchall()

    items = [_row_to_task_response(r) for r in rows]
    return TaskListResponse(items=items, total=total, page=page, page_size=page_size)


def get_task(task_id: int, owner_user_id: int) -> TaskDetailResponse:
    with get_cursor() as cursor:
        row = _check_task_owner(cursor, task_id, owner_user_id)

        cursor.execute(
            """SELECT asset_type, version, created_at
               FROM task_assets WHERE task_id = %s ORDER BY created_at DESC""",
            (task_id,),
        )
        asset_rows = cursor.fetchall()

    task = _row_to_task_response(row)
    assets = [
        TaskAssetResponse(
            asset_type=r["asset_type"],
            version=r["version"],
            created_at=str(r["created_at"]),
        )
        for r in asset_rows
    ]
    return TaskDetailResponse(task=task, assets=assets)


def update_task(task_id: int, request: UpdateTaskRequest, owner_user_id: int) -> TaskResponse:
    with get_cursor() as cursor:
        # Verify ownership first
        _check_task_owner(cursor, task_id, owner_user_id)

        updates: list[str] = []
        params: list[Any] = []

        if request.name is not None:
            updates.append("name = %s")
            params.append(request.name)
        if request.description is not None:
            updates.append("description = %s")
            params.append(request.description)
        if request.target_url is not None:
            updates.append("target_url = %s")
            params.append(request.target_url)
        if request.status is not None:
            updates.append("status = %s")
            params.append(request.status)

        if not updates:
            cursor.execute(
                """SELECT id, name, description, target_url, status, created_at, updated_at
                   FROM tasks WHERE id = %s""",
                (task_id,),
            )
            return _row_to_task_response(cursor.fetchone())

        updates.append("updated_at = %s")
        params.append(_now())
        updates.append("updated_by_user_id = %s")
        params.append(owner_user_id)
        params.append(task_id)

        cursor.execute(
            f"UPDATE tasks SET {', '.join(updates)} WHERE id = %s", params
        )
        cursor.execute(
            """SELECT id, name, description, target_url, status, created_at, updated_at
               FROM tasks WHERE id = %s""",
            (task_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise TaskNotFoundError(f"Task {task_id} not found")

    return _row_to_task_response(row)


def delete_task(task_id: int, owner_user_id: int) -> TaskResponse:
    now = _now()
    with get_cursor() as cursor:
        # Verify ownership first
        _check_task_owner(cursor, task_id, owner_user_id)

        cursor.execute(
            "UPDATE tasks SET status = 'archived', updated_at = %s WHERE id = %s",
            (now, task_id),
        )
        cursor.execute(
            """SELECT id, name, description, target_url, status, created_at, updated_at
               FROM tasks WHERE id = %s""",
            (task_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise TaskNotFoundError(f"Task {task_id} not found")

    return _row_to_task_response(row)


# -- Asset services ----------------------------------------------------------


def save_assets(task_id: int, assets: dict[str, Any], owner_user_id: int) -> SaveAssetResponse:
    for asset_type in assets.keys():
        if asset_type not in VALID_ASSET_TYPES:
            raise ValueError(
                f"Invalid asset type: {asset_type}. "
                f"Must be one of {sorted(VALID_ASSET_TYPES)}"
            )

    now = _now()
    versions: dict[str, int] = {}

    with get_cursor() as cursor:
        # Verify task ownership before saving assets
        _check_task_owner(cursor, task_id, owner_user_id)

        for asset_type, content in assets.items():
            # FOR UPDATE locks the row, preventing concurrent duplicate versions
            cursor.execute(
                """SELECT MAX(version) AS max_ver
                   FROM task_assets
                   WHERE task_id = %s AND asset_type = %s
                   FOR UPDATE""",
                (task_id, asset_type),
            )
            row = cursor.fetchone()
            new_version = (row["max_ver"] or 0) + 1

            cursor.execute(
                """INSERT INTO task_assets
                   (task_id, asset_type, content, version, created_at)
                   VALUES (%s, %s, %s, %s, %s)""",
                (task_id, asset_type, content, new_version, now),
            )
            versions[asset_type] = new_version

    return SaveAssetResponse(saved_count=len(assets), versions=versions)


def get_asset(task_id: int, asset_type: str, owner_user_id: int) -> dict[str, Any]:
    if asset_type not in VALID_ASSET_TYPES:
        raise ValueError(
            f"Invalid asset type: {asset_type}. "
            f"Must be one of {sorted(VALID_ASSET_TYPES)}"
        )

    with get_cursor() as cursor:
        # Verify task ownership before fetching assets
        _check_task_owner(cursor, task_id, owner_user_id)

        cursor.execute(
            """SELECT content, asset_type, version, created_at
               FROM task_assets
               WHERE task_id = %s AND asset_type = %s
               ORDER BY version DESC LIMIT 1""",
            (task_id, asset_type),
        )
        row = cursor.fetchone()

    if row is None:
        return {
            "content": None,
            "asset_type": asset_type,
            "version": 0,
            "created_at": None,
        }

    return {
        "content": row["content"],
        "asset_type": row["asset_type"],
        "version": row["version"],
        "created_at": str(row["created_at"]),
    }


# -- Helpers -----------------------------------------------------------------


def _row_to_task_response(row: dict) -> TaskResponse:
    return TaskResponse(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        target_url=row["target_url"],
        status=row["status"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )

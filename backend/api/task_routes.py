"""RESTful API routes for task CRUD operations.

All endpoints require authentication via the CurrentUser dependency.
Non-owner access returns 404 (not 403) to prevent task-ID enumeration.
Unauthenticated access returns 401.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from backend.auth.dependencies import AuthenticatedUser, require_auth
from backend.core.api_response import api_response
from backend.tasks.schemas import (
    CreateTaskRequest,
    GetAssetResponse,
    SaveAssetRequest,
    TaskDetailResponse,
    TaskListResponse,
    TaskResponse,
    UpdateTaskRequest,
)
from backend.tasks.services import (
    TaskNotFoundError,
    create_task,
    delete_task,
    get_asset,
    get_task,
    list_tasks,
    save_assets,
    update_task,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
CurrentUser = Annotated[AuthenticatedUser, Depends(require_auth)]

_INTERNAL_ERROR_MSG = "An unexpected error occurred. Please try again later."


@router.get("")
def list_tasks_endpoint(
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_archived: bool = Query(False),
):
    """List tasks with pagination. Only returns tasks owned by the current user."""
    try:
        result = list_tasks(
            owner_user_id=current_user.user_id,
            page=page,
            page_size=page_size,
            include_archived=include_archived,
        )
        return api_response(result)
    except Exception:
        logger.exception("Unexpected error listing tasks")
        return api_response(
            status_code=500, success=False,
            error_code="list_tasks_error", error=_INTERNAL_ERROR_MSG,
        )


@router.post("")
def create_task_endpoint(request: CreateTaskRequest, current_user: CurrentUser):
    """Create a new task. Owner is automatically set to the current user."""
    try:
        task = create_task(request, owner_user_id=current_user.user_id)
        return api_response({"task": task.model_dump()})
    except Exception:
        logger.exception("Unexpected error creating task")
        return api_response(
            status_code=500, success=False,
            error_code="create_task_error", error=_INTERNAL_ERROR_MSG,
        )


@router.get("/{task_id}")
def get_task_endpoint(task_id: int, current_user: CurrentUser):
    """Get task detail including asset metadata. Only the owner can access."""
    try:
        detail = get_task(task_id, owner_user_id=current_user.user_id)
        return api_response({"task": detail.task.model_dump(), "assets": [a.model_dump() for a in detail.assets]})
    except TaskNotFoundError as e:
        return api_response(status_code=404, success=False, error_code="task_not_found", error=str(e))
    except Exception:
        logger.exception("Unexpected error getting task %s", task_id)
        return api_response(
            status_code=500, success=False,
            error_code="get_task_error", error=_INTERNAL_ERROR_MSG,
        )


@router.put("/{task_id}")
def update_task_endpoint(task_id: int, request: UpdateTaskRequest, current_user: CurrentUser):
    """Partially update a task. Only the owner can update. Sets updated_by_user_id."""
    try:
        task = update_task(task_id, request, owner_user_id=current_user.user_id)
        return api_response({"task": task.model_dump()})
    except TaskNotFoundError as e:
        return api_response(status_code=404, success=False, error_code="task_not_found", error=str(e))
    except Exception:
        logger.exception("Unexpected error updating task %s", task_id)
        return api_response(
            status_code=500, success=False,
            error_code="update_task_error", error=_INTERNAL_ERROR_MSG,
        )


@router.delete("/{task_id}")
def delete_task_endpoint(task_id: int, current_user: CurrentUser):
    """Soft delete a task by setting status to 'archived'. Only the owner can delete."""
    try:
        task = delete_task(task_id, owner_user_id=current_user.user_id)
        return api_response({"task": task.model_dump()})
    except TaskNotFoundError as e:
        return api_response(status_code=404, success=False, error_code="task_not_found", error=str(e))
    except Exception:
        logger.exception("Unexpected error deleting task %s", task_id)
        return api_response(
            status_code=500, success=False,
            error_code="delete_task_error", error=_INTERNAL_ERROR_MSG,
        )


@router.post("/{task_id}/assets")
def save_assets_endpoint(task_id: int, request: SaveAssetRequest, current_user: CurrentUser):
    """Save or update assets for a task. Only the owner can save assets."""
    try:
        result = save_assets(task_id, request.assets, owner_user_id=current_user.user_id)
        return api_response({"saved_count": result.saved_count, "versions": result.versions})
    except TaskNotFoundError as e:
        return api_response(status_code=404, success=False, error_code="task_not_found", error=str(e))
    except ValueError as e:
        return api_response(status_code=400, success=False, error_code="invalid_asset", error=str(e))
    except Exception:
        logger.exception("Unexpected error saving assets for task %s", task_id)
        return api_response(
            status_code=500, success=False,
            error_code="save_assets_error", error=_INTERNAL_ERROR_MSG,
        )


@router.get("/{task_id}/assets/{asset_type}")
def get_asset_endpoint(task_id: int, asset_type: str, current_user: CurrentUser):
    """Get the latest version of a specific asset type for a task. Only the owner can access."""
    try:
        result = get_asset(task_id, asset_type, owner_user_id=current_user.user_id)
        return api_response(result)
    except TaskNotFoundError as e:
        return api_response(status_code=404, success=False, error_code="task_not_found", error=str(e))
    except ValueError as e:
        error_str = str(e)
        if "not found" in error_str.lower():
            return api_response(status_code=404, success=False, error_code="not_found", error=error_str)
        return api_response(status_code=400, success=False, error_code="invalid_asset", error=error_str)
    except Exception:
        logger.exception("Unexpected error getting asset %s for task %s", asset_type, task_id)
        return api_response(
            status_code=500, success=False,
            error_code="get_asset_error", error=_INTERNAL_ERROR_MSG,
        )

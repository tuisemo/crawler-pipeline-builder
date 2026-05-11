"""RESTful API routes for task CRUD operations."""

from fastapi import APIRouter, Query

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
    create_task,
    delete_task,
    get_asset,
    get_task,
    list_tasks,
    save_assets,
    update_task,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("")
def list_tasks_endpoint(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_archived: bool = Query(False),
):
    """List tasks with pagination. By default excludes archived tasks."""
    result = list_tasks(page=page, page_size=page_size, include_archived=include_archived)
    return api_response(result)


@router.post("")
def create_task_endpoint(request: CreateTaskRequest):
    """Create a new task with name required. Optional fields default to null."""
    try:
        task = create_task(request)
        return api_response({"task": task.model_dump()})
    except Exception as e:
        return api_response(status_code=400, success=False, error_code="create_task_error", error=str(e))


@router.get("/{task_id}")
def get_task_endpoint(task_id: int):
    """Get task detail including asset metadata."""
    try:
        detail = get_task(task_id)
        return api_response({"task": detail.task.model_dump(), "assets": [a.model_dump() for a in detail.assets]})
    except ValueError as e:
        return api_response(status_code=404, success=False, error_code="task_not_found", error=str(e))
    except Exception as e:
        return api_response(status_code=400, success=False, error_code="get_task_error", error=str(e))


@router.put("/{task_id}")
def update_task_endpoint(task_id: int, request: UpdateTaskRequest):
    """Partially update a task. Only provided fields are updated."""
    try:
        task = update_task(task_id, request)
        return api_response({"task": task.model_dump()})
    except ValueError as e:
        return api_response(status_code=404, success=False, error_code="task_not_found", error=str(e))
    except Exception as e:
        return api_response(status_code=400, success=False, error_code="update_task_error", error=str(e))


@router.delete("/{task_id}")
def delete_task_endpoint(task_id: int):
    """Soft delete a task by setting status to 'archived'."""
    try:
        task = delete_task(task_id)
        return api_response({"task": task.model_dump()})
    except ValueError as e:
        return api_response(status_code=404, success=False, error_code="task_not_found", error=str(e))
    except Exception as e:
        return api_response(status_code=400, success=False, error_code="delete_task_error", error=str(e))


@router.post("/{task_id}/assets")
def save_assets_endpoint(task_id: int, request: SaveAssetRequest):
    """Save or update assets for a task. Multiple asset types can be saved at once."""
    try:
        result = save_assets(task_id, request.assets)
        return api_response({"saved_count": result.saved_count, "versions": result.versions})
    except ValueError as e:
        return api_response(status_code=400, success=False, error_code="invalid_asset", error=str(e))
    except Exception as e:
        return api_response(status_code=400, success=False, error_code="save_assets_error", error=str(e))


@router.get("/{task_id}/assets/{asset_type}")
def get_asset_endpoint(task_id: int, asset_type: str):
    """Get the latest version of a specific asset type for a task."""
    try:
        result = get_asset(task_id, asset_type)
        return api_response(result)
    except ValueError as e:
        error_str = str(e)
        if "not found" in error_str.lower():
            return api_response(status_code=404, success=False, error_code="not_found", error=error_str)
        return api_response(status_code=400, success=False, error_code="invalid_asset", error=error_str)
    except Exception as e:
        return api_response(status_code=400, success=False, error_code="get_asset_error", error=str(e))

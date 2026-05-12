"""Tests for task CRUD API endpoints.

All task endpoints now require authentication.  This module creates a
test user and session before each test so that every request carries a
valid session cookie.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from backend.auth.session import create_session, upsert_user
from backend.database import get_cursor, run_migrations
from server import app


@pytest.fixture(autouse=True)
def _setup_auth_environment(monkeypatch: pytest.MonkeyPatch):
    """Set up database and auth environment for each test."""
    monkeypatch.setenv("USER_CENTER_BASE_URI", "https://user-center.example.com")
    monkeypatch.setenv("USER_CENTER_CLIENT_ID", "crawler-client")
    monkeypatch.setenv("USER_CENTER_CLIENT_SECRET", "crawler-secret")
    monkeypatch.setenv("SESSION_COOKIE_NAME", "session_token")
    monkeypatch.delenv("ENV", raising=False)

    run_migrations()

    with get_cursor() as cur:
        cur.execute("DELETE FROM task_assets")
        cur.execute("DELETE FROM tasks")
        cur.execute("DELETE FROM sessions")
        cur.execute("DELETE FROM users")


@pytest.fixture()
def test_user():
    """Create a test user and return (user_dict, session_token)."""
    user = upsert_user(external_id="openId_task_test", display_name="Task Tester")
    token = create_session(user_id=user["id"])
    return {"user": user, "token": token}


@pytest.fixture()
def client(test_user):
    """TestClient with session cookie pre-set for authenticated access."""
    token = test_user["token"]
    with TestClient(app) as c:
        c.cookies.set("session_token", token)
        yield c


# ----------------------------------------------------------------------
# Create task tests
# ----------------------------------------------------------------------


def test_create_task_with_full_fields(client: TestClient):
    """POST /api/tasks with full fields returns 200 with task object."""
    response = client.post(
        "/api/tasks",
        json={
            "name": "Test Task",
            "description": "A test task",
            "target_url": "https://example.com",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert "task" in data
    task = data["task"]
    assert task["name"] == "Test Task"
    assert task["description"] == "A test task"
    assert task["target_url"] == "https://example.com"
    assert task["status"] == "draft"
    assert "id" in task
    assert "created_at" in task
    assert "updated_at" in task


def test_create_task_with_name_only(client: TestClient):
    """POST /api/tasks with name only returns description=null, target_url=null."""
    response = client.post("/api/tasks", json={"name": "Minimal Task"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    task = payload["data"]["task"]
    assert task["name"] == "Minimal Task"
    assert task["description"] is None
    assert task["target_url"] is None
    assert task["status"] == "draft"


def test_create_task_without_name_fails(client: TestClient):
    """POST /api/tasks without name returns 422 validation error."""
    response = client.post("/api/tasks", json={})

    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False


# ----------------------------------------------------------------------
# List tasks tests
# ----------------------------------------------------------------------


def test_list_tasks_returns_paginated_items(client: TestClient):
    """GET /api/tasks returns paginated {items, total, page, page_size}."""
    # Create a few tasks
    for i in range(3):
        client.post("/api/tasks", json={"name": f"Task {i}"})

    response = client.get("/api/tasks")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert data["total"] == 3
    assert len(data["items"]) == 3


def test_list_tasks_excludes_archived(client: TestClient):
    """GET /api/tasks excludes archived tasks by default."""
    # Create and archive a task
    create_resp = client.post("/api/tasks", json={"name": "To Archive"})
    task_id = create_resp.json()["data"]["task"]["id"]
    client.delete(f"/api/tasks/{task_id}")

    # Create another task
    client.post("/api/tasks", json={"name": "Active Task"})

    response = client.get("/api/tasks")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Active Task"


def test_list_tasks_with_pagination(client: TestClient):
    """GET /api/tasks supports page and page_size parameters."""
    # Create 5 tasks
    for i in range(5):
        client.post("/api/tasks", json={"name": f"Task {i}"})

    # Get first page with page_size=2
    response = client.get("/api/tasks?page=1&page_size=2")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["items"]) == 2


def test_list_tasks_include_archived(client: TestClient):
    """GET /api/tasks?include_archived=true includes archived tasks."""
    # Create and archive a task
    create_resp = client.post("/api/tasks", json={"name": "To Archive"})
    task_id = create_resp.json()["data"]["task"]["id"]
    client.delete(f"/api/tasks/{task_id}")

    response = client.get("/api/tasks?include_archived=true")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1


# ----------------------------------------------------------------------
# Get task detail tests
# ----------------------------------------------------------------------


def test_get_task_returns_detail_with_assets(client: TestClient):
    """GET /api/tasks/{id} returns {task: {...}, assets: [...]}."""
    # Create a task
    create_resp = client.post("/api/tasks", json={"name": "Detail Test"})
    task_id = create_resp.json()["data"]["task"]["id"]

    response = client.get(f"/api/tasks/{task_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert "task" in data
    assert "assets" in data
    assert data["task"]["name"] == "Detail Test"
    assert isinstance(data["assets"], list)


def test_get_task_not_found(client: TestClient):
    """GET /api/tasks/{id} for non-existent task returns 404."""
    response = client.get("/api/tasks/99999")

    assert response.status_code == 404
    payload = response.json()
    assert payload["success"] is False
    assert payload["error_code"] == "task_not_found"


# ----------------------------------------------------------------------
# Update task tests
# ----------------------------------------------------------------------


def test_update_task_partial_update(client: TestClient):
    """PUT /api/tasks/{id} with partial fields only updates provided fields."""
    # Create a task
    create_resp = client.post(
        "/api/tasks",
        json={"name": "Original", "description": "Original desc", "target_url": "https://original.com"},
    )
    task_id = create_resp.json()["data"]["task"]["id"]

    # Update only name
    response = client.put(f"/api/tasks/{task_id}", json={"name": "Updated Name"})

    assert response.status_code == 200
    task = response.json()["data"]["task"]
    assert task["name"] == "Updated Name"
    assert task["description"] == "Original desc"  # Unchanged
    assert task["target_url"] == "https://original.com"  # Unchanged


def test_update_task_updates_timestamp(client: TestClient):
    """PUT /api/tasks/{id} updates the updated_at timestamp."""
    # Create a task
    create_resp = client.post("/api/tasks", json={"name": "Time Test"})
    task_id = create_resp.json()["data"]["task"]["id"]
    original_updated_at = create_resp.json()["data"]["task"]["updated_at"]

    # Update
    import time
    time.sleep(0.01)  # Small delay to ensure different timestamp
    response = client.put(f"/api/tasks/{task_id}", json={"name": "Time Test Updated"})
    new_updated_at = response.json()["data"]["task"]["updated_at"]

    assert new_updated_at != original_updated_at


def test_update_task_not_found(client: TestClient):
    """PUT /api/tasks/{id} for non-existent task returns 404."""
    response = client.put("/api/tasks/99999", json={"name": "New Name"})

    assert response.status_code == 404
    payload = response.json()
    assert payload["success"] is False


# ----------------------------------------------------------------------
# Delete task tests (soft delete)
# ----------------------------------------------------------------------


def test_delete_task_soft_deletes(client: TestClient):
    """DELETE /api/tasks/{id} sets status='archived'."""
    # Create a task
    create_resp = client.post("/api/tasks", json={"name": "To Delete"})
    task_id = create_resp.json()["data"]["task"]["id"]

    # Delete
    response = client.delete(f"/api/tasks/{task_id}")

    assert response.status_code == 200
    task = response.json()["data"]["task"]
    assert task["status"] == "archived"


def test_delete_task_disappears_from_default_list(client: TestClient):
    """DELETE /api/tasks/{id} - task disappears from default list."""
    # Create a task
    create_resp = client.post("/api/tasks", json={"name": "To Delete"})
    task_id = create_resp.json()["data"]["task"]["id"]

    # Delete
    client.delete(f"/api/tasks/{task_id}")

    # List should not include it
    response = client.get("/api/tasks")
    data = response.json()["data"]
    assert data["total"] == 0


def test_delete_task_still_accessible_by_id(client: TestClient):
    """DELETE /api/tasks/{id} - task is still accessible by ID with status='archived'."""
    # Create a task
    create_resp = client.post("/api/tasks", json={"name": "To Delete"})
    task_id = create_resp.json()["data"]["task"]["id"]

    # Delete
    client.delete(f"/api/tasks/{task_id}")

    # Still accessible by ID
    response = client.get(f"/api/tasks/{task_id}")
    task = response.json()["data"]["task"]
    assert task["status"] == "archived"


def test_delete_task_not_found(client: TestClient):
    """DELETE /api/tasks/{id} for non-existent task returns 404."""
    response = client.delete("/api/tasks/99999")

    assert response.status_code == 404
    payload = response.json()
    assert payload["success"] is False


# ----------------------------------------------------------------------
# Asset tests
# ----------------------------------------------------------------------


def test_save_assets(client: TestClient):
    """POST /api/tasks/{id}/assets saves assets and returns saved_count and versions."""
    # Create a task
    create_resp = client.post("/api/tasks", json={"name": "Asset Test"})
    task_id = create_resp.json()["data"]["task"]["id"]

    response = client.post(
        f"/api/tasks/{task_id}/assets",
        json={"assets": {"workflow_graph": '{"nodes": [], "edges": []}', "prompt": "Test prompt"}},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["saved_count"] == 2
    assert data["versions"]["workflow_graph"] == 1
    assert data["versions"]["prompt"] == 1


def test_save_assets_increments_version(client: TestClient):
    """Saving the same asset type again increments the version."""
    # Create a task
    create_resp = client.post("/api/tasks", json={"name": "Version Test"})
    task_id = create_resp.json()["data"]["task"]["id"]

    # Save once
    client.post(f"/api/tasks/{task_id}/assets", json={"assets": {"workflow_graph": "v1"}})
    # Save again
    response = client.post(f"/api/tasks/{task_id}/assets", json={"assets": {"workflow_graph": "v2"}})

    data = response.json()["data"]
    assert data["versions"]["workflow_graph"] == 2


def test_save_assets_invalid_type(client: TestClient):
    """Saving an invalid asset type returns 400."""
    # Create a task
    create_resp = client.post("/api/tasks", json={"name": "Invalid Asset Test"})
    task_id = create_resp.json()["data"]["task"]["id"]

    response = client.post(f"/api/tasks/{task_id}/assets", json={"assets": {"invalid_type": "content"}})

    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert "invalid_asset" in payload["error_code"].lower() or "invalid" in payload["error"].lower()


def test_save_assets_task_not_found(client: TestClient):
    """Saving assets to non-existent task returns 404."""
    response = client.post("/api/tasks/99999/assets", json={"assets": {"workflow_graph": "{}"}})

    assert response.status_code == 404  # TaskNotFoundError returns 404


def test_get_asset(client: TestClient):
    """GET /api/tasks/{id}/assets/{type} returns asset content."""
    # Create a task and save asset
    create_resp = client.post("/api/tasks", json={"name": "Get Asset Test"})
    task_id = create_resp.json()["data"]["task"]["id"]
    client.post(f"/api/tasks/{task_id}/assets", json={"assets": {"workflow_graph": '{"nodes": []}'}})

    response = client.get(f"/api/tasks/{task_id}/assets/workflow_graph")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["content"] == '{"nodes": []}'
    assert data["version"] == 1
    assert data["asset_type"] == "workflow_graph"


def test_get_asset_not_found(client: TestClient):
    """GET /api/tasks/{id}/assets/{type} for non-existent asset returns content null."""
    # Create a task without saving the asset
    create_resp = client.post("/api/tasks", json={"name": "No Asset Test"})
    task_id = create_resp.json()["data"]["task"]["id"]

    response = client.get(f"/api/tasks/{task_id}/assets/workflow_graph")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["content"] is None
    assert data["version"] == 0


# ----------------------------------------------------------------------
# Error envelope tests
# ----------------------------------------------------------------------


def test_all_error_responses_use_envelope(client: TestClient):
    """All error cases return proper envelope with error_code and error message."""
    # Get a non-existent task
    response = client.get("/api/tasks/99999")
    payload = response.json()

    assert "success" in payload
    assert "error_code" in payload
    assert "error" in payload
    assert "data" in payload
    assert payload["success"] is False
    assert payload["error_code"] == "task_not_found"

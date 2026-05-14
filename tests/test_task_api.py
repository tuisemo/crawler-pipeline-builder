"""Tests for task CRUD API endpoints.

All task endpoints now require authentication.
"""

from __future__ import annotations

import pytest
import fakeredis
from fastapi.testclient import TestClient

from backend.auth.session import create_session, upsert_user
from backend.database import get_cursor, run_migrations
from server import app


@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    fake_r = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("backend.auth.redis_client.get_redis", lambda: fake_r)
    return fake_r


@pytest.fixture(autouse=True)
def _setup_auth_environment(monkeypatch: pytest.MonkeyPatch):
    """Set up database and auth environment for each test."""
    monkeypatch.setenv("USER_CENTER_BASE_URI", "https://user-center.example.com")
    monkeypatch.setenv("USER_CENTER_CLIENT_ID", "crawler-client")
    monkeypatch.setenv("USER_CENTER_CLIENT_SECRET", "crawler-secret")
    monkeypatch.delenv("ENV", raising=False)

    run_migrations()
    with get_cursor() as cur:
        cur.execute("DELETE FROM task_assets")
        cur.execute("DELETE FROM tasks")
        cur.execute("DELETE FROM users")


@pytest.fixture()
def test_user():
    """Create a test user and return (user_dict, session_token)."""
    user = upsert_user(external_id="openId_task_test", display_name="Task Tester")
    token = create_session(user_id=user["id"])
    return {"user": user, "token": token}


@pytest.fixture()
def client(test_user):
    """TestClient with Authorization bearer header pre-set for authenticated access."""
    token = test_user["token"]
    with TestClient(app) as c:
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c


def test_create_task_with_full_fields(client: TestClient):
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
    assert payload["data"]["task"]["name"] == "Test Task"


def test_list_tasks_returns_paginated_items(client: TestClient):
    client.post("/api/tasks", json={"name": "Task 1"})
    client.post("/api/tasks", json={"name": "Task 2"})

    response = client.get("/api/tasks")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 2


def test_get_task_not_found(client: TestClient):
    response = client.get("/api/tasks/99999")
    assert response.status_code == 404
    assert response.json()["error_code"] == "task_not_found"


def test_update_task_partial_update(client: TestClient):
    create_resp = client.post("/api/tasks", json={"name": "Original"})
    task_id = create_resp.json()["data"]["task"]["id"]

    response = client.put(f"/api/tasks/{task_id}", json={"name": "Updated"})
    assert response.status_code == 200
    assert response.json()["data"]["task"]["name"] == "Updated"


def test_delete_task_soft_deletes(client: TestClient):
    create_resp = client.post("/api/tasks", json={"name": "To Delete"})
    task_id = create_resp.json()["data"]["task"]["id"]

    response = client.delete(f"/api/tasks/{task_id}")
    assert response.status_code == 200
    assert response.json()["data"]["task"]["status"] == "archived"


def test_save_assets(client: TestClient):
    create_resp = client.post("/api/tasks", json={"name": "Asset Test"})
    task_id = create_resp.json()["data"]["task"]["id"]

    response = client.post(
        f"/api/tasks/{task_id}/assets",
        json={"assets": {"workflow_graph": '{"nodes": []}'}},
    )
    assert response.status_code == 200
    assert response.json()["data"]["saved_count"] == 1


def test_get_asset(client: TestClient):
    create_resp = client.post("/api/tasks", json={"name": "Get Asset Test"})
    task_id = create_resp.json()["data"]["task"]["id"]
    client.post(f"/api/tasks/{task_id}/assets", json={"assets": {"workflow_graph": '{"nodes": []}'}})

    response = client.get(f"/api/tasks/{task_id}/assets/workflow_graph")
    assert response.status_code == 200
    assert response.json()["data"]["content"] == '{"nodes": []}'

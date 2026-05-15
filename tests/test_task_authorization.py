"""Tests for task CRUD owner-based authorization.

Covers validation contract assertions:
- VAL-TASK-001: Task creation auto-assigns owner to current user
- VAL-TASK-002: Task list returns only tasks owned by current user
- VAL-TASK-003: Non-owner access to single task returns 404
- VAL-TASK-004: Non-owner update to task returns 404
- VAL-TASK-005: Non-owner delete of task returns 404
- VAL-TASK-006: task_assets inherit owner constraint from parent task
- VAL-TASK-007: Batch operations respect owner constraint
- VAL-TASK-008: Unauthenticated task access returns 401, not 404
"""

from __future__ import annotations

import pytest

from backend.auth.session import create_session, upsert_user
from backend.database import get_cursor


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture()
def alice():
    """Create Alice user and return user dict + session token."""
    user = upsert_user(external_id="openId_alice", display_name="Alice", email="alice@example.com")
    token = create_session(user_id=user["id"])
    return {"user": user, "token": token}


@pytest.fixture()
def bob():
    """Create Bob user and return user dict + session token."""
    user = upsert_user(external_id="openId_bob", display_name="Bob", email="bob@example.com")
    token = create_session(user_id=user["id"])
    return {"user": user, "token": token}


def _create_task_via_api(client: TestClient, token: str, name: str = "Test Task") -> dict:
    """Helper: create a task via API and return the response JSON data."""
    response = client.post(
        "/api/tasks",
        json={"name": name, "description": "test description", "target_url": "https://example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, f"Failed to create task: {response.json()}"
    return response.json()["data"]


# ── VAL-TASK-001: Task creation auto-assigns owner ─────────────────────


class TestTaskCreateOwner:
    """create_task auto-sets owner_user_id = current_user.id, ignores any owner field in request body."""

    def test_create_task_auto_sets_owner(self, client, alice):
        """Created task's owner_user_id must be the authenticated user's id."""
        data = _create_task_via_api(client, alice['token'], "Alice task")
        task_id = data["task"]["id"]

        with get_cursor() as cur:
            cur.execute("SELECT owner_user_id FROM tasks WHERE id = %s", (task_id,))
            row = cur.fetchone()

        assert row["owner_user_id"] == alice["user"]["id"]

    def test_create_task_ignores_owner_field_in_body(self, client, alice, bob):
        """Even if the request body includes an 'owner' field, it must be ignored."""
        response = client.post(
            "/api/tasks",
            json={
                "name": "Attempt owner hijack",
                "owner_user_id": bob["user"]["id"],  # should be ignored
            },
            headers={"Authorization": f"Bearer {alice['token']}"},
        )
        assert response.status_code == 200
        task_id = response.json()["data"]["task"]["id"]

        with get_cursor() as cur:
            cur.execute("SELECT owner_user_id FROM tasks WHERE id = %s", (task_id,))
            row = cur.fetchone()

        # owner must still be alice, not bob
        assert row["owner_user_id"] == alice["user"]["id"]

    def test_create_task_requires_authentication(self, client):
        """Unauthenticated request to create task must return 401."""
        response = client.post(
            "/api/tasks",
            json={"name": "No auth task"},
        )
        assert response.status_code == 401


# ── VAL-TASK-002: Task list filters by owner ───────────────────────────


class TestTaskListOwnerFilter:
    """list_tasks only returns tasks WHERE owner_user_id = current_user.id."""

    def test_list_tasks_only_returns_own_tasks(self, client, alice, bob):
        """Each user only sees their own tasks in the list."""
        _create_task_via_api(client, alice['token'], "Alice task 1")
        _create_task_via_api(client, alice['token'], "Alice task 2")
        _create_task_via_api(client, bob['token'], "Bob task 1")

        # Alice sees 2 tasks
        alice_response = client.get("/api/tasks", headers={"Authorization": f"Bearer {alice['token']}"})
        assert alice_response.status_code == 200
        alice_data = alice_response.json()["data"]
        assert alice_data["total"] == 2
        assert all(t["name"].startswith("Alice") for t in alice_data["items"])

        # Bob sees 1 task
        bob_response = client.get("/api/tasks", headers={"Authorization": f"Bearer {bob['token']}"})
        assert bob_response.status_code == 200
        bob_data = bob_response.json()["data"]
        assert bob_data["total"] == 1
        assert bob_data["items"][0]["name"] == "Bob task 1"

    def test_list_tasks_requires_authentication(self, client):
        """Unauthenticated request to list tasks must return 401."""
        response = client.get("/api/tasks")
        assert response.status_code == 401

    def test_empty_list_for_user_with_no_tasks(self, client, bob):
        """A user with no tasks sees an empty list."""
        response = client.get("/api/tasks", headers={"Authorization": f"Bearer {bob['token']}"})
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 0
        assert data["items"] == []


# ── VAL-TASK-003: Non-owner read returns 404 ───────────────────────────


class TestTaskGetOwnerCheck:
    """get_task returns task only if owner, otherwise 404."""

    def test_owner_can_get_own_task(self, client, alice):
        """Owner can retrieve their own task."""
        task_data = _create_task_via_api(client, alice['token'], "Alice task")
        task_id = task_data["task"]["id"]

        response = client.get(f"/api/tasks/{task_id}", headers={"Authorization": f"Bearer {alice['token']}"})
        assert response.status_code == 200
        assert response.json()["data"]["task"]["id"] == task_id

    def test_non_owner_gets_404(self, client, alice, bob):
        """Non-owner accessing another user's task gets 404."""
        task_data = _create_task_via_api(client, alice['token'], "Alice task")
        task_id = task_data["task"]["id"]

        response = client.get(f"/api/tasks/{task_id}", headers={"Authorization": f"Bearer {bob['token']}"})
        assert response.status_code == 404

    def test_non_owner_404_same_as_truly_not_found(self, client, alice, bob):
        """Non-owner 404 response body is identical to truly-not-found 404 (prevents enumeration)."""
        task_data = _create_task_via_api(client, alice['token'], "Alice task")
        task_id = task_data["task"]["id"]

        # Non-owner access
        non_owner_response = client.get(f"/api/tasks/{task_id}", headers={"Authorization": f"Bearer {bob['token']}"})
        assert non_owner_response.status_code == 404

        # Truly non-existent task
        not_found_response = client.get("/api/tasks/999999", headers={"Authorization": f"Bearer {bob['token']}"})
        assert not_found_response.status_code == 404

        # Both should have the same error_code and detail structure
        non_owner_body = non_owner_response.json()
        not_found_body = not_found_response.json()
        assert non_owner_body["error_code"] == not_found_body["error_code"]

    def test_get_task_requires_authentication(self, client, alice):
        """Unauthenticated request to get task must return 401."""
        task_data = _create_task_via_api(client, alice['token'], "Alice task")
        task_id = task_data["task"]["id"]

        # Use a fresh client without cookies
        response = client.get(f"/api/tasks/{task_id}")
        assert response.status_code == 401


# ── VAL-TASK-004: Non-owner update returns 404 ─────────────────────────


class TestTaskUpdateOwnerCheck:
    """update_task returns 404 if not owner, and sets updated_by_user_id."""

    def test_owner_can_update_own_task(self, client, alice):
        """Owner can update their own task."""
        task_data = _create_task_via_api(client, alice['token'], "Original name")
        task_id = task_data["task"]["id"]

        response = client.put(
            f"/api/tasks/{task_id}",
            json={"name": "Updated name"},
            headers={"Authorization": f"Bearer {alice['token']}"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["task"]["name"] == "Updated name"

    def test_non_owner_update_returns_404(self, client, alice, bob):
        """Non-owner updating another user's task gets 404."""
        task_data = _create_task_via_api(client, alice['token'], "Alice task")
        task_id = task_data["task"]["id"]

        response = client.put(
            f"/api/tasks/{task_id}",
            json={"name": "Hijacked name"},
            headers={"Authorization": f"Bearer {bob['token']}"},
        )
        assert response.status_code == 404

        # Verify the task was NOT modified
        verify_response = client.get(f"/api/tasks/{task_id}", headers={"Authorization": f"Bearer {alice['token']}"})
        assert verify_response.status_code == 200
        assert verify_response.json()["data"]["task"]["name"] == "Alice task"

    def test_update_task_sets_updated_by_user_id(self, client, alice):
        """update_task sets updated_by_user_id = current_user.id."""
        task_data = _create_task_via_api(client, alice['token'], "Alice task")
        task_id = task_data["task"]["id"]

        client.put(
            f"/api/tasks/{task_id}",
            json={"name": "Updated by Alice"},
            headers={"Authorization": f"Bearer {alice['token']}"},
        )

        with get_cursor() as cur:
            cur.execute("SELECT updated_by_user_id FROM tasks WHERE id = %s", (task_id,))
            row = cur.fetchone()

        assert row["updated_by_user_id"] == alice["user"]["id"]

    def test_update_task_requires_authentication(self, client, alice):
        """Unauthenticated request to update task must return 401."""
        task_data = _create_task_via_api(client, alice['token'], "Alice task")
        task_id = task_data["task"]["id"]

        response = client.put(
            f"/api/tasks/{task_id}",
            json={"name": "No auth update"},
        )
        assert response.status_code == 401


# ── VAL-TASK-005: Non-owner delete returns 404 ─────────────────────────


class TestTaskDeleteOwnerCheck:
    """delete_task returns 404 if not owner."""

    def test_owner_can_delete_own_task(self, client, alice):
        """Owner can delete (archive) their own task."""
        task_data = _create_task_via_api(client, alice['token'], "Alice task")
        task_id = task_data["task"]["id"]

        response = client.delete(f"/api/tasks/{task_id}", headers={"Authorization": f"Bearer {alice['token']}"})
        assert response.status_code == 200

    def test_non_owner_delete_returns_404(self, client, alice, bob):
        """Non-owner deleting another user's task gets 404."""
        task_data = _create_task_via_api(client, alice['token'], "Alice task")
        task_id = task_data["task"]["id"]

        response = client.delete(f"/api/tasks/{task_id}", headers={"Authorization": f"Bearer {bob['token']}"})
        assert response.status_code == 404

        # Verify the task still exists and is not archived
        verify_response = client.get(f"/api/tasks/{task_id}", headers={"Authorization": f"Bearer {alice['token']}"})
        assert verify_response.status_code == 200
        assert verify_response.json()["data"]["task"]["status"] == "draft"

    def test_delete_task_requires_authentication(self, client, alice):
        """Unauthenticated request to delete task must return 401."""
        task_data = _create_task_via_api(client, alice['token'], "Alice task")
        task_id = task_data["task"]["id"]

        response = client.delete(f"/api/tasks/{task_id}")
        assert response.status_code == 401


# ── VAL-TASK-006: task_assets inherit owner constraint ─────────────────


class TestTaskAssetOwnerCheck:
    """save_assets and get_asset check task ownership (404 if not owner)."""

    def test_owner_can_save_assets(self, client, alice):
        """Owner can save assets to their own task."""
        task_data = _create_task_via_api(client, alice['token'], "Alice task")
        task_id = task_data["task"]["id"]

        response = client.post(
            f"/api/tasks/{task_id}/assets",
            json={"assets": {"workflow_graph": '{"nodes": [], "edges": []}'}},
            headers={"Authorization": f"Bearer {alice['token']}"},
        )
        assert response.status_code == 200

    def test_owner_can_get_assets(self, client, alice):
        """Owner can get assets from their own task."""
        task_data = _create_task_via_api(client, alice['token'], "Alice task")
        task_id = task_data["task"]["id"]

        # Save an asset first
        client.post(
            f"/api/tasks/{task_id}/assets",
            json={"assets": {"workflow_graph": '{"nodes": [], "edges": []}'}},
            headers={"Authorization": f"Bearer {alice['token']}"},
        )

        # Get the asset
        response = client.get(
            f"/api/tasks/{task_id}/assets/workflow_graph",
            headers={"Authorization": f"Bearer {alice['token']}"},
        )
        assert response.status_code == 200

    def test_non_owner_save_assets_returns_404(self, client, alice, bob):
        """Non-owner saving assets to another user's task gets 404."""
        task_data = _create_task_via_api(client, alice['token'], "Alice task")
        task_id = task_data["task"]["id"]

        response = client.post(
            f"/api/tasks/{task_id}/assets",
            json={"assets": {"workflow_graph": '{"nodes": []}'}},
            headers={"Authorization": f"Bearer {bob['token']}"},
        )
        assert response.status_code == 404

    def test_non_owner_get_assets_returns_404(self, client, alice, bob):
        """Non-owner getting assets from another user's task gets 404."""
        task_data = _create_task_via_api(client, alice['token'], "Alice task")
        task_id = task_data["task"]["id"]

        # Save an asset as Alice
        client.post(
            f"/api/tasks/{task_id}/assets",
            json={"assets": {"workflow_graph": '{"nodes": [], "edges": []}'}},
            headers={"Authorization": f"Bearer {alice['token']}"},
        )

        # Try to get the asset as Bob
        response = client.get(
            f"/api/tasks/{task_id}/assets/workflow_graph",
            headers={"Authorization": f"Bearer {bob['token']}"},
        )
        assert response.status_code == 404

    def test_save_assets_requires_authentication(self, client, alice):
        """Unauthenticated request to save assets must return 401."""
        task_data = _create_task_via_api(client, alice['token'], "Alice task")
        task_id = task_data["task"]["id"]

        response = client.post(
            f"/api/tasks/{task_id}/assets",
            json={"assets": {"workflow_graph": '{"nodes": []}'}},
        )
        assert response.status_code == 401

    def test_get_assets_requires_authentication(self, client, alice):
        """Unauthenticated request to get assets must return 401."""
        task_data = _create_task_via_api(client, alice['token'], "Alice task")
        task_id = task_data["task"]["id"]

        response = client.get(f"/api/tasks/{task_id}/assets/workflow_graph")
        assert response.status_code == 401


# ── VAL-TASK-007: Batch operations respect owner constraint ─────────────


class TestBatchOwnerConstraint:
    """Batch/list endpoints only return the current user's tasks."""

    def test_list_with_include_archived_only_shows_own_tasks(self, client, alice, bob):
        """include_archived=True still only shows the current user's tasks."""
        _create_task_via_api(client, alice['token'], "Alice task 1")
        _create_task_via_api(client, bob['token'], "Bob task 1")

        # Alice archives her task
        alice_tasks = client.get("/api/tasks", headers={"Authorization": f"Bearer {alice['token']}"})
        alice_task_id = alice_tasks.json()["data"]["items"][0]["id"]
        client.delete(f"/api/tasks/{alice_task_id}", headers={"Authorization": f"Bearer {alice['token']}"})

        # Alice sees her archived task with include_archived=True
        response = client.get(
            "/api/tasks",
            params={"include_archived": True},
            headers={"Authorization": f"Bearer {alice['token']}"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["status"] == "archived"

        # Bob's tasks are not visible
        bob_names = [t["name"] for t in data["items"]]
        assert "Bob task 1" not in bob_names


# ── VAL-TASK-008: Unauthenticated task access returns 401 ──────────────


class TestUnauthenticatedTaskAccess:
    """Unauthenticated access to any task API must return 401, not 404."""

    def test_unauthenticated_list_tasks_returns_401(self, client):
        response = client.get("/api/tasks")
        assert response.status_code == 401

    def test_unauthenticated_create_task_returns_401(self, client):
        response = client.post("/api/tasks", json={"name": "test"})
        assert response.status_code == 401

    def test_unauthenticated_get_task_returns_401(self, client):
        response = client.get("/api/tasks/1")
        assert response.status_code == 401

    def test_unauthenticated_update_task_returns_401(self, client):
        response = client.put("/api/tasks/1", json={"name": "test"})
        assert response.status_code == 401

    def test_unauthenticated_delete_task_returns_401(self, client):
        response = client.delete("/api/tasks/1")
        assert response.status_code == 401

    def test_unauthenticated_save_assets_returns_401(self, client):
        response = client.post("/api/tasks/1/assets", json={"assets": {"workflow_graph": "{}"}})
        assert response.status_code == 401

    def test_unauthenticated_get_asset_returns_401(self, client):
        response = client.get("/api/tasks/1/assets/workflow_graph")
        assert response.status_code == 401

    def test_authenticated_non_owner_gets_404_not_401(self, client, alice, bob):
        """Authenticated non-owner gets 404 (not 401) — 401 is only for unauthenticated."""
        task_data = _create_task_via_api(client, alice['token'], "Alice task")
        task_id = task_data["task"]["id"]

        response = client.get(f"/api/tasks/{task_id}", headers={"Authorization": f"Bearer {bob['token']}"})
        assert response.status_code == 404  # NOT 401



import shutil
from pathlib import Path

import pytest
import fakeredis
from fastapi.testclient import TestClient
from backend.auth.session import create_session, upsert_user
from backend.database import get_cursor, run_migrations
from backend.workflow.services import LEGACY_CONFIG_DEPRECATION_WARNING
from server import app


@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    fake_r = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("backend.auth.redis_client.get_redis", lambda: fake_r)
    return fake_r


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _setup_auth_for_workflow(client, monkeypatch, mock_redis):
    """Set up authentication for all workflow API tests."""
    monkeypatch.setenv("USER_CENTER_BASE_URI", "https://user-center.example.com")
    monkeypatch.setenv("USER_CENTER_CLIENT_ID", "crawler-client")
    monkeypatch.setenv("USER_CENTER_CLIENT_SECRET", "crawler-secret")
    monkeypatch.setenv("USER_CENTER_SCOPE", "basic")
    monkeypatch.setenv("USER_CENTER_REDIRECT_URI", "http://testserver/auth/callback")
    monkeypatch.delenv("ENV", raising=False)

    run_migrations()
    with get_cursor() as cur:
        cur.execute("DELETE FROM task_assets")
        cur.execute("DELETE FROM tasks")
        cur.execute("DELETE FROM users")

    user = upsert_user(
        external_id="openId_workflow_test",
        display_name="Workflow Tester",
        email="wf@test.com",
    )
    token = create_session(user_id=user["id"])
    client.headers.update({"Authorization": f"Bearer {token}"})


def response_data(response):
    body = response.json()
    assert body["success"] is True
    return body["data"]


def test_validate_workflow_valid(client):
    response = client.post("/api/workflows/validate", json={
        "graph": {
            "nodes": [
                {"id": "n1", "type": "open_page", "data": {"url": "http://a.com"}}
            ],
            "edges": []
        }
    })
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_from_legacy_config_valid(client):
    response = client.post("/api/workflows/from-legacy-config", json={
        "url": "http://example.com",
        "item_selector": ".item",
        "fields": [{"name": "title", "selector": "h1", "type": "text"}],
    })
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert LEGACY_CONFIG_DEPRECATION_WARNING in response.json()["warnings"][0]["message"]


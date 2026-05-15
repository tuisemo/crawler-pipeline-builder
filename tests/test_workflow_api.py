import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from backend.auth.session import create_session, upsert_user
from server import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _setup_auth_for_workflow(client):
    """Set up authentication for all workflow API tests."""
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

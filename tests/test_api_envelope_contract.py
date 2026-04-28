from fastapi.testclient import TestClient

from server import app


client = TestClient(app)


def test_workflow_success_response_uses_transport_envelope_only():
    response = client.post(
        "/api/workflows/validate",
        json={"graph": {"nodes": [{"id": "n1", "type": "open_page", "data": {"url": "http://example.com"}}], "edges": []}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "success": True,
        "error_code": None,
        "error": None,
        "data": {"message": "Workflow is valid"},
        "warnings": [],
        "meta": {},
    }


def test_workflow_domain_fields_are_nested_under_data():
    response = client.post(
        "/api/workflows/from-legacy-config",
        json={
            "url": "http://example.com",
            "item_selector": ".item",
            "fields": [{"name": "title", "selector": "h1", "type": "text"}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "graph" not in payload
    assert payload["data"]["graph"]["nodes"][0]["type"] == "open_page"


def test_validation_errors_use_the_same_envelope():
    response = client.post("/api/workflows/validate", json={})

    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["error_code"] == "request_validation_error"
    assert payload["data"] == {}
    assert payload["meta"]["detail"]

import pytest
from fastapi.testclient import TestClient
from server import app

client = TestClient(app)

def test_validate_workflow_missing_graph():
    response = client.post("/api/workflows/validate", json={})
    assert response.status_code == 422 # Pydantic validation error

def test_validate_workflow_empty_nodes():
    response = client.post("/api/workflows/validate", json={"graph": {"nodes": [], "edges": []}})
    assert response.status_code == 400
    assert "least one node" in response.json()["error"]

def test_validate_workflow_missing_entry():
    response = client.post("/api/workflows/validate", json={
        "graph": {
            "nodes": [
                {"id": "n1", "type": "select_list", "data": {"item_selector": ".item"}}
            ],
            "edges": []
        }
    })
    assert response.status_code == 400
    assert "entry node" in response.json()["error"]

def test_validate_workflow_multiple_entries():
    response = client.post("/api/workflows/validate", json={
        "graph": {
            "nodes": [
                {"id": "n1", "type": "open_page", "data": {"url": "http://a.com"}},
                {"id": "n2", "type": "open_page", "data": {"url": "http://b.com"}}
            ],
            "edges": []
        }
    })
    assert response.status_code == 400
    assert "only have one" in response.json()["error"]

def test_validate_workflow_valid():
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

def test_from_legacy_config_missing_url():
    response = client.post("/api/workflows/from-legacy-config", json={
        "item_selector": ".item",
        "fields": []
    })
    assert response.status_code == 422 # Pydantic requires url

def test_from_legacy_config_missing_item_selector():
    response = client.post("/api/workflows/from-legacy-config", json={
        "url": "http://example.com",
        "fields": []
    })
    assert response.status_code == 422 # Pydantic requires item_selector

def test_from_legacy_config_valid():
    response = client.post("/api/workflows/from-legacy-config", json={
        "url": "http://example.com",
        "item_selector": ".item",
        "fields": [{"name": "title", "selector": "h1"}],
        "pagination_selector": ".next",
        "pagination_strategy": "click_next",
        "max_pages": 5
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    
    graph = data["graph"]
    nodes = graph["nodes"]
    
    assert len(nodes) == 4
    assert nodes[0]["type"] == "open_page"
    assert nodes[0]["data"]["url"] == "http://example.com"
    
    assert nodes[1]["type"] == "select_list"
    assert nodes[1]["data"]["item_selector"] == ".item"
    
    assert nodes[2]["type"] == "extract_field"
    assert len(nodes[2]["data"]["fields"]) == 1
    assert nodes[2]["data"]["fields"][0]["name"] == "title"
    
    assert nodes[3]["type"] == "paginate"
    assert nodes[3]["data"]["pagination_selector"] == ".next"
    assert nodes[3]["data"]["pagination_strategy"] == "click_next"
    assert nodes[3]["data"]["max_pages"] == 5

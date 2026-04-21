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

def test_from_legacy_config_blank_critical_values_return_400():
    response = client.post("/api/workflows/from-legacy-config", json={
        "url": "   ",
        "item_selector": ".item",
        "fields": []
    })
    assert response.status_code == 400
    assert response.json()["success"] is False
    assert "URL and item_selector are required" in response.json()["error"]

    response = client.post("/api/workflows/from-legacy-config", json={
        "url": "http://example.com",
        "item_selector": "",
        "fields": []
    })
    assert response.status_code == 400
    assert response.json()["success"] is False
    assert "URL and item_selector are required" in response.json()["error"]


def test_from_legacy_config_valid():
    fields = [{
        "name": "title",
        "selector": "h1",
        "type": "text",
        "extraction_type": "text",
        "custom_key": "preserved",
    }]
    response = client.post("/api/workflows/from-legacy-config", json={
        "url": "http://example.com",
        "item_selector": ".item",
        "fields": fields,
        "pagination_selector": ".next",
        "pagination_strategy": "click_next",
        "max_pages": 5,
        "html_fragment": "<article>Sample</article>",
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["warnings"] == []
    
    graph = data["graph"]
    nodes = graph["nodes"]
    edges = graph["edges"]
    
    assert [node["id"] for node in nodes] == ["node_1", "node_2", "node_3", "node_4"]
    assert [node["type"] for node in nodes] == ["open_page", "select_list", "extract_field", "paginate"]
    assert edges == [
        {"id": "edge_1_2", "source": "node_1", "target": "node_2"},
        {"id": "edge_2_3", "source": "node_2", "target": "node_3"},
        {"id": "edge_3_4", "source": "node_3", "target": "node_4"},
    ]
    assert nodes[0]["data"]["url"] == "http://example.com"
    assert nodes[1]["data"]["item_selector"] == ".item"
    assert nodes[2]["data"]["fields"] == fields
    assert nodes[2]["data"]["html_fragment"] == "<article>Sample</article>"
    assert nodes[3]["data"]["pagination_selector"] == ".next"
    assert nodes[3]["data"]["pagination_strategy"] == "click_next"
    assert nodes[3]["data"]["max_pages"] == 5


def test_from_legacy_config_omits_pagination_node_when_selector_omitted():
    response = client.post("/api/workflows/from-legacy-config", json={
        "url": "http://example.com",
        "item_selector": ".item",
        "fields": [{"name": "title", "selector": "h1", "type": "text"}],
    })

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["warnings"] == []

    graph = data["graph"]
    assert [node["type"] for node in graph["nodes"]] == ["open_page", "select_list", "extract_field"]
    assert graph["edges"] == [
        {"id": "edge_1_2", "source": "node_1", "target": "node_2"},
        {"id": "edge_2_3", "source": "node_2", "target": "node_3"},
    ]
    assert graph["nodes"][2]["data"]["html_fragment"] == ""

def test_to_prompt_missing_graph():
    response = client.post("/api/workflows/to-prompt", json={})
    assert response.status_code == 422 # Pydantic validation error

def test_to_prompt_missing_url():
    response = client.post("/api/workflows/to-prompt", json={
        "graph": {
            "nodes": [
                {"id": "n1", "type": "select_list", "data": {"item_selector": ".item"}}
            ],
            "edges": []
        }
    })
    assert response.status_code == 400
    assert "URL and item_selector are required" in response.json()["error"]

def test_to_prompt_valid():
    response = client.post("/api/workflows/to-prompt", json={
        "graph": {
            "nodes": [
                {"id": "n1", "type": "open_page", "data": {"url": "http://example.com"}},
                {"id": "n2", "type": "select_list", "data": {"item_selector": ".item"}},
                {"id": "n3", "type": "extract_field", "data": {"fields": [{"name": "title", "selector": "h1"}]}}
            ],
            "edges": []
        }
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "http://example.com" in data["prompt"]
    assert ".item" in data["prompt"]
    assert "title" in data["prompt"]

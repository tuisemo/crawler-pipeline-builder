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


# ----------------------------------------------------------------------
# DSL Validation tests (more detailed error_code checks)
# ----------------------------------------------------------------------


def post_validate(graph):
    return client.post("/api/workflows/validate", json={"graph": graph})


def test_validate_requires_graph_nodes_and_edges_arrays():
    assert client.post("/api/workflows/validate", json={}).status_code == 422
    assert client.post("/api/workflows/validate", json={"graph": {"edges": []}}).status_code == 422
    assert client.post("/api/workflows/validate", json={"graph": {"nodes": []}}).status_code == 422


def test_validate_requires_node_id_type_and_data_shape():
    graph = {"nodes": [{"type": "open_page", "data": {}}], "edges": []}
    assert post_validate(graph).status_code == 422

    graph = {"nodes": [{"id": "n1", "data": {}}], "edges": []}
    assert post_validate(graph).status_code == 422

    graph = {"nodes": [{"id": "n1", "type": "open_page"}], "edges": []}
    assert post_validate(graph).status_code == 422

    graph = {"nodes": [{"id": 123, "type": "open_page", "data": {}}], "edges": []}
    assert post_validate(graph).status_code == 422


def test_validate_requires_edge_id_source_and_target_shape():
    nodes = [{"id": "n1", "type": "open_page", "data": {}}]
    assert post_validate({"nodes": nodes, "edges": [{"source": "n1", "target": "n2"}]}).status_code == 422
    assert post_validate({"nodes": nodes, "edges": [{"id": "e1", "target": "n2"}]}).status_code == 422
    assert post_validate({"nodes": nodes, "edges": [{"id": "e1", "source": "n1"}]}).status_code == 422
    assert post_validate({"nodes": nodes, "edges": [{"id": "e1", "source": 1, "target": "n2"}]}).status_code == 422


def test_validate_rejects_empty_missing_and_multiple_entry_nodes_with_machine_errors():
    empty = post_validate({"nodes": [], "edges": []})
    assert empty.status_code == 400
    assert empty.json()["error_code"] == "workflow_empty"

    missing = post_validate({"nodes": [{"id": "n1", "type": "select_list", "data": {}}], "edges": []})
    assert missing.status_code == 400
    assert missing.json()["error_code"] == "entry_node_missing"

    multiple = post_validate({
        "nodes": [
            {"id": "n1", "type": "open_page", "data": {}},
            {"id": "n2", "type": "open_page", "data": {}},
        ],
        "edges": [],
    })
    assert multiple.status_code == 400
    assert multiple.json()["error_code"] == "entry_node_multiple"


def test_validate_rejects_duplicate_node_and_edge_ids_with_machine_errors():
    duplicate_nodes = post_validate({
        "nodes": [
            {"id": "n1", "type": "open_page", "data": {}},
            {"id": "n1", "type": "select_list", "data": {}},
        ],
        "edges": [],
    })
    assert duplicate_nodes.status_code == 400
    assert duplicate_nodes.json()["error_code"] == "duplicate_node_ids"

    duplicate_edges = post_validate({
        "nodes": [{"id": "n1", "type": "open_page", "data": {}}],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e1", "source": "n2", "target": "n3"},
        ],
    })
    assert duplicate_edges.status_code == 400
    assert duplicate_edges.json()["error_code"] == "duplicate_edge_ids"


def test_validate_minimal_valid_graph_succeeds():
    response = post_validate({"nodes": [{"id": "n1", "type": "open_page", "data": {}}], "edges": []})
    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "Workflow is valid"}


def test_validate_mvp_accepts_structural_graph_with_optional_legacy_data_and_unknown_nodes():
    response = post_validate({
        "nodes": [
            {
                "id": "n1",
                "type": "open_page",
                "data": {
                    "url": "https://example.com",
                    "item_selector": ".item",
                    "fields": [{"name": "title", "selector": "h1", "type": "text"}],
                    "pagination_selector": ".next",
                    "pagination_strategy": "click_next",
                    "max_pages": 2,
                    "html_fragment": "<div></div>",
                    "max_items": 3,
                    "max_steps": 4,
                    "future_option": "accepted",
                },
            },
            {"id": "n2", "type": "custom_future_node", "data": {"url": "ignored", "custom": "allowed"}},
        ],
        "edges": [{"id": "e1", "source": "missing-source", "target": "n2"}],
    })
    assert response.status_code == 200
    assert response.json()["success"] is True

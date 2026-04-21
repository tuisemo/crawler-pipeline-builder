from fastapi.testclient import TestClient

from server import app


client = TestClient(app)


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

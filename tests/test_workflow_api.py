import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from server import app
from backend.workflow_schemas import AssistLlmResponse, AutoDetectResponse

client = TestClient(app)


def make_test_workspace(name: str) -> Path:
    root = Path(__file__).resolve().parent / ".tmp" / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root

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
    assert "Selector Compatibility Contract" in data["prompt"]
    assert data["editable_prompt"] == data["prompt"]
    assert "Execution Plan (Deterministic)" in data["effective_prompt"]
    assert "Output Strategy (In-Memory)" in data["effective_prompt"]


# ----------------------------------------------------------------------
# Generate Crawler tests
# ----------------------------------------------------------------------


def test_generate_crawler_missing_graph():
    response = client.post("/api/workflows/generate-crawler", json={})
    assert response.status_code == 422  # Pydantic validation error

def test_generate_crawler_missing_url():
    response = client.post("/api/workflows/generate-crawler", json={
        "graph": {
            "nodes": [
                {"id": "n1", "type": "select_list", "data": {"item_selector": ".item"}}
            ],
            "edges": []
        }
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "URL and item_selector are required" in data["error"]

def test_generate_crawler_missing_item_selector():
    response = client.post("/api/workflows/generate-crawler", json={
        "graph": {
            "nodes": [
                {"id": "n1", "type": "open_page", "data": {"url": "http://example.com"}}
            ],
            "edges": []
        }
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "URL and item_selector are required" in data["error"]

def test_generate_crawler_valid_without_llm(monkeypatch):
    """Test that generate-crawler returns a structured response without real LLM I/O."""
    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            from llm_client import LLMResponse
            return LLMResponse(content="print('ok')", model="fake-model", usage={"prompt_tokens": 1, "completion_tokens": 1})

    monkeypatch.setattr("backend.workflow_services.get_default_client", lambda: FakeClient())

    response = client.post("/api/workflows/generate-crawler", json={
        "graph": {
            "nodes": [
                {"id": "n1", "type": "open_page", "data": {"url": "http://example.com"}},
                {"id": "n2", "type": "select_list", "data": {"item_selector": ".item"}},
                {"id": "n3", "type": "extract_field", "data": {"fields": [{"name": "title", "selector": "h1", "type": "text"}]}}
            ],
            "edges": []
        }
    })
    data = response.json()
    assert data["success"] is True
    assert "Execution Plan (Deterministic)" in data["prompt"]
    assert "Output Strategy (In-Memory)" in data["prompt"]
    assert "Non-Negotiable Implementation Guardrails" in data["prompt"]
    assert "Deterministic Skeleton (Reference Base)" in data["prompt"]
    assert data["generation_mode"] == "lite"
    assert data["generation_trace"][0]["stage"] == "draft_generation"


def test_generate_skeleton_missing_graph():
    response = client.post("/api/workflows/generate-skeleton", json={})
    assert response.status_code == 422


def test_generate_skeleton_missing_required_fields():
    response = client.post("/api/workflows/generate-skeleton", json={
        "graph": {
            "nodes": [{"id": "n1", "type": "open_page", "data": {"url": "http://example.com"}}],
            "edges": [],
        }
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "URL and item_selector are required" in data["error"]


def test_generate_skeleton_valid():
    response = client.post("/api/workflows/generate-skeleton", json={
        "graph": {
            "nodes": [
                {"id": "n1", "type": "open_page", "data": {"url": "http://example.com"}},
                {"id": "n2", "type": "select_list", "data": {"item_selector": ".item"}},
                {
                    "id": "n3",
                    "type": "extract_field",
                    "data": {"fields": [{"name": "title", "selector": "h1", "type": "text", "clean_data_type": "text"}]},
                },
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3"},
            ],
        }
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["filename"] == "crawler_skeleton.py"
    assert "sync_playwright" in data["script"]
    assert "ENTRY_URL = 'http://example.com'" in data["script"]
    assert "NORMALIZATION_RULES" in data["script"]


def test_format_script_endpoint_returns_formatted_content():
    response = client.post("/api/workflows/format-script", json={
        "content": "def run():\r\n\treturn 1\r\n",
        "language": "python",
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["formatted_content"] == "def run():\n    return 1\n"


def test_save_script_endpoint_persists_file(monkeypatch):
    workspace_root = make_test_workspace("api-save-script")
    monkeypatch.setattr("backend.workflow_services.WORKSPACE_ROOT", workspace_root)

    response = client.post("/api/workflows/save-script", json={
        "relative_path": "generated/api_saved.py",
        "content": "print('saved')",
        "overwrite": False,
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["relative_path"] == "generated/api_saved.py"
    assert (workspace_root / "generated" / "api_saved.py").read_text(encoding="utf-8") == "print('saved')\n"


def test_save_script_endpoint_rejects_existing_target_without_overwrite(monkeypatch):
    workspace_root = make_test_workspace("api-save-script-existing")
    monkeypatch.setattr("backend.workflow_services.WORKSPACE_ROOT", workspace_root)
    target = workspace_root / "generated" / "existing.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("print('first')\n", encoding="utf-8")

    response = client.post("/api/workflows/save-script", json={
        "relative_path": "generated/existing.py",
        "content": "print('second')",
        "overwrite": False,
    })

    assert response.status_code == 400
    payload = response.json()
    assert payload["error_code"] == "target_exists"


def test_compile_plan_valid():
    response = client.post("/api/workflows/compile-plan", json={
        "graph": {
            "nodes": [
                {"id": "n1", "type": "open_page", "data": {"url": "http://example.com"}},
                {"id": "n2", "type": "select_list", "data": {"item_selector": ".item", "max_items": 3}},
                {"id": "n3", "type": "extract_field", "data": {"fields": [{"name": "title", "selector": "h1", "type": "text"}]}},
                {"id": "n4", "type": "condition", "data": {"condition": "not_exists title", "expression_mode": "simple"}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3"},
                {"id": "e3", "source": "n3", "target": "n4"},
                {"id": "e4", "source": "n4", "target": "n3", "branch": "true", "order": 0},
            ]
        }
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["plan"]["entry_url"] == "http://example.com"
    assert data["plan"]["item_selector"] == ".item"
    assert data["plan"]["limits"]["max_items"] == 3
    assert data["plan"]["field_specs"][0]["name"] == "title"
    assert any(edge["branch"] == "true" for edge in data["plan"]["edges"])


def test_assist_auto_detect_surfaces_session_errors(monkeypatch):
    monkeypatch.setattr(
        "backend.assist_routes.auto_detect",
        lambda _request: AutoDetectResponse(success=False, error="No active browser session found"),
    )
    response = client.post("/api/assist/auto-detect", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "No active browser session found" in data["error"]


def test_assist_extract_html_reports_total_match_count_not_sample_size(monkeypatch):
    class FakeItem:
        def __init__(self, html: str):
            self._html = html

        def inner_html(self):
            return self._html

    class FakePage:
        def query_selector_all(self, _selector: str):
            return [FakeItem(f"<div>item-{idx}</div>") for idx in range(5)]

    class FakeSession:
        id = "session-1"
        page = FakePage()

    monkeypatch.setattr("backend.assist_services._ensure_session", lambda session_id, url: (FakeSession(), None))

    response = client.post("/api/assist/extract-html", json={
        "item_selector": ".item",
        "max_items": 3,
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["metadata"]["item_count"] == 5
    assert "item-0" in payload["html_fragment"]
    assert "item-2" in payload["html_fragment"]
    assert "item-3" not in payload["html_fragment"]


def test_assist_extract_html_can_include_pagination_context(monkeypatch):
    class FakeItem:
        def __init__(self, html: str):
            self._html = html

        def inner_html(self):
            return self._html

        def evaluate(self, _script: str):
            return f"<div class='item'>{self._html}</div>"

    class FakeControl:
        def __init__(self, text: str, href: str = ""):
            self._text = text
            self._href = href

        def inner_text(self):
            return self._text

        def get_attribute(self, name: str):
            if name == "href":
                return self._href
            return ""

    class FakePager:
        def evaluate(self, _script: str):
            return '<div class="kq-pager"><span class="current">1</span><a href="/list?p=2">2</a><a href="/list?p=2">下一页</a></div>'

        def inner_text(self):
            return "1 2 下一页"

        def query_selector_all(self, selector: str):
            if selector == 'a, button, [role="button"], span':
                return [FakeControl("1"), FakeControl("2", "/list?p=2"), FakeControl("下一页", "/list?p=2")]
            return []

        def get_attribute(self, name: str):
            if name == "class":
                return "kq-pager"
            if name == "id":
                return ""
            return ""

    class FakePage:
        def query_selector_all(self, selector: str):
            if selector == ".item":
                return [FakeItem(f"<div>item-{idx}</div>") for idx in range(5)]
            if selector == ".kq-pager":
                return [FakePager()]
            return []

    class FakeSession:
        id = "session-1"
        page = FakePage()

    monkeypatch.setattr("backend.assist_services._ensure_session", lambda session_id, url: (FakeSession(), None))

    response = client.post("/api/assist/extract-html", json={
        "item_selector": ".item",
        "max_items": 3,
        "include_pagination": True,
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["metadata"]["item_count"] == 5
    assert "下一页" in payload["html_fragment"]
    assert "kq-pager" in payload["html_fragment"]


def test_assist_clean_data_requires_raw_data_and_type():
    response = client.post("/api/assist/clean-data", json={})
    assert response.status_code == 422


def test_assist_clean_data_success(monkeypatch):
    def fake_clean_data(_request):
        return AssistLlmResponse(
            success=True,
            result={"cleaned_value": 12000, "confidence": 0.91},
            reason="normalized count suffix",
        )

    monkeypatch.setattr("backend.assist_routes.clean_data", fake_clean_data)

    response = client.post("/api/assist/clean-data", json={
        "raw_data": "1.2万条评论",
        "data_type": "count",
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["result"]["cleaned_value"] == 12000


def test_full_flow_from_legacy_to_compile_and_skeleton():
    legacy = client.post("/api/workflows/from-legacy-config", json={
        "url": "http://example.com",
        "item_selector": ".item",
        "fields": [
            {
                "name": "price",
                "selector": ".price",
                "type": "text",
                "clean_data_type": "price",
                "normalized_sample": "1234.56",
            }
        ],
        "pagination_selector": ".next",
        "pagination_strategy": "click_next",
        "max_pages": 3,
    })
    assert legacy.status_code == 200
    legacy_payload = legacy.json()
    assert legacy_payload["success"] is True
    graph = legacy_payload["graph"]

    validate = client.post("/api/workflows/validate", json={"graph": graph})
    assert validate.status_code == 200
    assert validate.json()["success"] is True

    compile_resp = client.post("/api/workflows/compile-plan", json={"graph": graph})
    assert compile_resp.status_code == 200
    compile_payload = compile_resp.json()
    assert compile_payload["success"] is True
    assert compile_payload["plan"]["field_specs"][0]["clean_data_type"] == "price"

    skeleton_resp = client.post("/api/workflows/generate-skeleton", json={"graph": graph})
    assert skeleton_resp.status_code == 200
    skeleton_payload = skeleton_resp.json()
    assert skeleton_payload["success"] is True
    assert "normalize_value" in skeleton_payload["script"]


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
    response = post_validate({
        "nodes": [{"id": "n1", "type": "open_page", "data": {"url": "http://example.com"}}],
        "edges": []
    })
    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "Workflow is valid"}


def test_validate_accepts_structural_graph_with_extra_supported_node_data():
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
        ],
        "edges": [],
    })
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_validate_rejects_unknown_node_types_and_dangling_edges():
    response = post_validate({
        "nodes": [
            {"id": "n1", "type": "open_page", "data": {"url": "https://example.com"}},
            {"id": "n2", "type": "custom_future_node", "data": {"custom": "allowed"}},
        ],
        "edges": [{"id": "e1", "source": "missing-source", "target": "n2"}],
    })
    assert response.status_code == 400
    assert response.json()["error_code"] == "edge_source_missing"


# ----------------------------------------------------------------------
# Phase 1 schema hardening: node-level required field validation
# ----------------------------------------------------------------------


def test_validate_open_page_requires_url():
    """open_page node without url is rejected at validation time."""
    response = post_validate({
        "nodes": [{"id": "n1", "type": "open_page", "data": {}}],
        "edges": [],
    })
    assert response.status_code == 400
    assert response.json()["error_code"] == "open_page_requires_url"

    # Also reject explicit blank url
    response = post_validate({
        "nodes": [{"id": "n1", "type": "open_page", "data": {"url": "   "}}],
        "edges": [],
    })
    assert response.status_code == 400
    assert response.json()["error_code"] == "open_page_requires_url"


def test_validate_select_list_requires_item_selector():
    """select_list node without item_selector is rejected at validation time."""
    # Need open_page entry first so we reach select_list validation
    response = post_validate({
        "nodes": [
            {"id": "n1", "type": "open_page", "data": {"url": "http://example.com"}},
            {"id": "n2", "type": "select_list", "data": {}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    })
    assert response.status_code == 400
    assert response.json()["error_code"] == "select_list_requires_item_selector"

    # Also reject explicit blank item_selector
    response = post_validate({
        "nodes": [
            {"id": "n1", "type": "open_page", "data": {"url": "http://example.com"}},
            {"id": "n2", "type": "select_list", "data": {"item_selector": ""}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    })
    assert response.status_code == 400
    assert response.json()["error_code"] == "select_list_requires_item_selector"


def test_validate_extract_field_requires_fields_list():
    """extract_field node without fields is rejected at validation time."""
    response = post_validate({
        "nodes": [
            {"id": "n1", "type": "open_page", "data": {"url": "http://example.com"}},
            {"id": "n2", "type": "select_list", "data": {"item_selector": ".item"}},
            {"id": "n3", "type": "extract_field", "data": {}},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},
        ],
    })
    assert response.status_code == 400
    assert response.json()["error_code"] == "extract_field_requires_fields"


def test_validate_extract_field_rejects_empty_fields_list():
    """extract_field node with empty fields list is rejected."""
    response = post_validate({
        "nodes": [
            {"id": "n1", "type": "open_page", "data": {"url": "http://example.com"}},
            {"id": "n2", "type": "select_list", "data": {"item_selector": ".item"}},
            {"id": "n3", "type": "extract_field", "data": {"fields": []}},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},
        ],
    })
    assert response.status_code == 400
    assert response.json()["error_code"] == "extract_field_requires_fields"


def test_validate_extract_field_accepts_valid_fields():
    """extract_field node with valid fields list passes validation."""
    response = post_validate({
        "nodes": [
            {
                "id": "n1", "type": "open_page",
                "data": {"url": "http://example.com"}
            },
            {
                "id": "n2", "type": "select_list",
                "data": {"item_selector": ".item"}
            },
            {
                "id": "n3",
                "type": "extract_field",
                "data": {
                    "fields": [
                        {"name": "title", "selector": "h1", "type": "text"},
                        {"field_name": "link", "css": "a", "extraction_type": "attr:href"},
                    ]
                }
            },
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},
        ],
    })
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_validate_extract_field_accepts_legacy_field_aliases():
    """extract_field fields using legacy aliases (field_name, css, extraction_type) pass validation."""
    response = post_validate({
        "nodes": [
            {"id": "n1", "type": "open_page", "data": {"url": "http://example.com"}},
            {"id": "n2", "type": "select_list", "data": {"item_selector": ".item"}},
            {
                "id": "n3",
                "type": "extract_field",
                "data": {"fields": [{"field_name": "title", "css": "h1", "extraction_type": "text"}]}
            },
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},
        ],
    })
    assert response.status_code == 200


def test_validate_extract_field_requires_field_name_and_selector():
    response = post_validate({
        "nodes": [
            {"id": "n1", "type": "open_page", "data": {"url": "http://example.com"}},
            {"id": "n2", "type": "select_list", "data": {"item_selector": ".item"}},
            {"id": "n3", "type": "extract_field", "data": {"fields": [{"selector": "h1"}]}},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},
        ],
    })
    assert response.status_code == 400
    assert response.json()["error_code"] == "extract_field_requires_field_name"

    response = post_validate({
        "nodes": [
            {"id": "n1", "type": "open_page", "data": {"url": "http://example.com"}},
            {"id": "n2", "type": "select_list", "data": {"item_selector": ".item"}},
            {"id": "n3", "type": "extract_field", "data": {"fields": [{"name": "title"}]}},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},
        ],
    })
    assert response.status_code == 400
    assert response.json()["error_code"] == "extract_field_requires_field_selector"


def test_validate_paginate_requires_pagination_selector():
    """paginate node without pagination_selector is rejected at validation time."""
    response = post_validate({
        "nodes": [
            {"id": "n1", "type": "open_page", "data": {"url": "http://example.com"}},
            {"id": "n2", "type": "select_list", "data": {"item_selector": ".item"}},
            {"id": "n3", "type": "extract_field", "data": {"fields": [{"name": "title", "selector": "h1"}]}},
            {"id": "n4", "type": "paginate", "data": {}},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},
            {"id": "e3", "source": "n3", "target": "n4"},
        ],
    })
    assert response.status_code == 400
    assert response.json()["error_code"] == "paginate_requires_pagination_selector"


def test_validate_paginate_accepts_valid_pagination_selector():
    """paginate node with valid pagination_selector passes validation."""
    response = post_validate({
        "nodes": [
            {"id": "n1", "type": "open_page", "data": {"url": "http://example.com"}},
            {"id": "n2", "type": "select_list", "data": {"item_selector": ".item"}},
            {"id": "n3", "type": "extract_field", "data": {"fields": [{"name": "title", "selector": "h1"}]}},
            {
                "id": "n4", "type": "paginate",
                "data": {"pagination_selector": ".next", "pagination_strategy": "click_next", "max_pages": 5}
            },
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},
            {"id": "e3", "source": "n3", "target": "n4"},
        ],
    })
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_validate_unknown_node_types_are_rejected():
    """Unsupported executor node types are rejected during validation."""
    response = post_validate({
        "nodes": [
            {"id": "n1", "type": "open_page", "data": {"url": "http://example.com"}},
            {"id": "n2", "type": "select_list", "data": {"item_selector": ".item"}},
            {"id": "n3", "type": "custom_script", "data": {}},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},
        ],
    })
    assert response.status_code == 400
    assert response.json()["error_code"] == "unsupported_node_type"

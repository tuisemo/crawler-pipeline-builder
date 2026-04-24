"""Regression tests for workflow services layer.

These tests verify that service functions:
1. Return domain results on success
2. Raise domain exceptions (not JSONResponse) on failure
"""

import shutil
from pathlib import Path

import pytest
from backend.workflow_schemas import (
    FormatScriptRequest,
    SaveScriptRequest,
    ValidateWorkflowRequest,
    WorkflowGraph,
    WorkflowNode,
    WorkflowEdge,
    NodeData,
    FromLegacyConfigRequest,
    ToPromptRequest,
    GenerateCrawlerRequest,
    CompilePlanRequest,
    GenerateSkeletonRequest,
)
from backend.workflow_services import (
    validate_graph,
    convert_legacy_config,
    compile_plan,
    format_script,
    graph_to_prompt,
    generate_skeleton,
    generate_crawler,
    save_script,
    WorkflowValidationError,
    WorkflowConversionError,
    PromptGenerationError,
    ScriptPersistenceError,
)
from backend.assist_services import clean_data
from backend.workflow_schemas import AssistCleanDataRequest, AssistLlmResponse


def make_test_workspace(name: str) -> Path:
    root = Path(__file__).resolve().parent / ".tmp" / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


# ----------------------------------------------------------------------
# validate_graph tests
# ----------------------------------------------------------------------

def test_validate_graph_returns_dict_on_success():
    """On success, validate_graph returns a plain dict, not a JSONResponse."""
    request = ValidateWorkflowRequest(
        graph=WorkflowGraph(
            nodes=[WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com"))],
            edges=[]
        )
    )
    result = validate_graph(request)
    assert isinstance(result, dict)
    assert result["success"] is True
    assert "message" in result


def test_validate_graph_raises_on_empty_nodes():
    """Empty nodes raises WorkflowValidationError, not JSONResponse."""
    request = ValidateWorkflowRequest(
        graph=WorkflowGraph(nodes=[], edges=[])
    )
    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_graph(request)
    assert exc_info.value.error_code == "workflow_empty"
    assert "at least one node" in exc_info.value.error


def test_validate_graph_raises_on_missing_entry():
    """Missing entry node raises WorkflowValidationError."""
    request = ValidateWorkflowRequest(
        graph=WorkflowGraph(
            nodes=[WorkflowNode(id="n1", type="select_list", data=NodeData(item_selector=".item"))],
            edges=[]
        )
    )
    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_graph(request)
    assert exc_info.value.error_code == "entry_node_missing"


def test_validate_graph_raises_on_multiple_entries():
    """Multiple entry nodes raises WorkflowValidationError."""
    request = ValidateWorkflowRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://a.com")),
                WorkflowNode(id="n2", type="open_page", data=NodeData(url="http://b.com")),
            ],
            edges=[]
        )
    )
    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_graph(request)
    assert exc_info.value.error_code == "entry_node_multiple"


def test_validate_graph_raises_on_duplicate_node_ids():
    """Duplicate node IDs raises WorkflowValidationError."""
    request = ValidateWorkflowRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://a.com")),
                WorkflowNode(id="n1", type="select_list", data=NodeData(item_selector=".item")),
            ],
            edges=[]
        )
    )
    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_graph(request)
    assert exc_info.value.error_code == "duplicate_node_ids"


def test_validate_graph_raises_on_duplicate_edge_ids():
    """Duplicate edge IDs raises WorkflowValidationError."""
    from backend.workflow_schemas import WorkflowEdge
    request = ValidateWorkflowRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://a.com")),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(id="n3", type="extract_field", data=NodeData(fields=[{"name": "title", "selector": "h1", "type": "text"}])),
            ],
            edges=[
                WorkflowEdge(id="e1", source="n1", target="n2"),
                WorkflowEdge(id="e1", source="n2", target="n3"),
            ]
        )
    )
    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_graph(request)
    assert exc_info.value.error_code == "duplicate_edge_ids"


def test_validate_graph_raises_on_missing_edge_source_reference():
    request = ValidateWorkflowRequest(
        graph=WorkflowGraph(
            nodes=[WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://a.com"))],
            edges=[WorkflowEdge(id="e1", source="missing", target="n1")],
        )
    )
    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_graph(request)
    assert exc_info.value.error_code == "edge_source_missing"


def test_validate_graph_raises_on_missing_edge_target_reference():
    request = ValidateWorkflowRequest(
        graph=WorkflowGraph(
            nodes=[WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://a.com"))],
            edges=[WorkflowEdge(id="e1", source="n1", target="missing")],
        )
    )
    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_graph(request)
    assert exc_info.value.error_code == "edge_target_missing"


def test_validate_graph_rejects_unsupported_node_types():
    request = ValidateWorkflowRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://a.com")),
                WorkflowNode(id="n2", type="custom_script", data=NodeData()),
            ],
            edges=[],
        )
    )
    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_graph(request)
    assert exc_info.value.error_code == "unsupported_node_type"


# ----------------------------------------------------------------------
# convert_legacy_config tests
# ----------------------------------------------------------------------

def test_convert_legacy_config_returns_domain_response_on_success():
    """On success, convert_legacy_config returns FromLegacyConfigResponse, not JSONResponse."""
    request = FromLegacyConfigRequest(
        url="http://example.com",
        item_selector=".item",
        fields=[{"name": "title", "selector": "h1", "type": "text"}]
    )
    result = convert_legacy_config(request)
    # Should return a domain response, not HTTP response
    assert result.success is True
    assert result.graph is not None
    assert len(result.graph.nodes) == 3  # open_page, select_list, extract_field


def test_convert_legacy_config_raises_on_blank_url():
    """Blank URL raises WorkflowConversionError, not JSONResponse."""
    request = FromLegacyConfigRequest(
        url="   ",
        item_selector=".item",
        fields=[]
    )
    with pytest.raises(WorkflowConversionError) as exc_info:
        convert_legacy_config(request)
    assert "URL and item_selector are required" in str(exc_info.value)


def test_convert_legacy_config_raises_on_blank_item_selector():
    """Blank item_selector raises WorkflowConversionError, not JSONResponse."""
    request = FromLegacyConfigRequest(
        url="http://example.com",
        item_selector="",
        fields=[]
    )
    with pytest.raises(WorkflowConversionError) as exc_info:
        convert_legacy_config(request)
    assert "URL and item_selector are required" in str(exc_info.value)


def test_convert_legacy_config_preserves_pagination_node():
    """When pagination_selector is provided, paginate node is included."""
    request = FromLegacyConfigRequest(
        url="http://example.com",
        item_selector=".item",
        fields=[{"name": "title", "selector": "h1", "type": "text"}],
        pagination_selector=".next"
    )
    result = convert_legacy_config(request)
    assert result.success is True
    assert len(result.graph.nodes) == 4  # includes paginate
    assert result.graph.nodes[3].type == "paginate"


# ----------------------------------------------------------------------
# graph_to_prompt tests
# ----------------------------------------------------------------------

def test_graph_to_prompt_returns_dict_on_success():
    """On success, graph_to_prompt returns a plain dict with prompt, not JSONResponse."""
    request = ToPromptRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com")),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(id="n3", type="extract_field", data=NodeData(fields=[{"name": "title", "selector": "h1", "type": "text"}])),
            ],
            edges=[]
        )
    )
    result = graph_to_prompt(request)
    assert isinstance(result, dict)
    assert result["success"] is True
    assert "prompt" in result
    assert result["editable_prompt"] == result["prompt"]
    assert "effective_prompt" in result
    assert "http://example.com" in result["prompt"]
    assert ".item" in result["prompt"]


def test_graph_to_prompt_raises_on_missing_url():
    """Missing URL raises PromptGenerationError, not JSONResponse."""
    request = ToPromptRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="select_list", data=NodeData(item_selector=".item")),
            ],
            edges=[]
        )
    )
    with pytest.raises(PromptGenerationError) as exc_info:
        graph_to_prompt(request)
    assert "URL and item_selector are required" in str(exc_info.value)


def test_graph_to_prompt_raises_on_missing_item_selector():
    """Missing item_selector raises PromptGenerationError, not JSONResponse."""
    request = ToPromptRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com")),
            ],
            edges=[]
        )
    )
    with pytest.raises(PromptGenerationError) as exc_info:
        graph_to_prompt(request)
    assert "URL and item_selector are required" in str(exc_info.value)


def test_compile_plan_returns_deterministic_plan():
    request = CompilePlanRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com", max_steps=12)),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item", max_items=4)),
                WorkflowNode(
                    id="n3",
                    type="extract_field",
                    data=NodeData(fields=[{"name": "title", "selector": "h1", "clean_data_type": "text"}]),
                ),
            ],
            edges=[
                WorkflowEdge(id="e1", source="n1", target="n2"),
                WorkflowEdge(id="e2", source="n2", target="n3"),
            ]
        )
    )
    result = compile_plan(request)
    assert result.success is True
    assert result.plan["entry_url"] == "http://example.com"
    assert result.plan["item_selector"] == ".item"
    assert result.plan["limits"]["max_items"] == 4
    assert result.plan["limits"]["max_steps"] == 12
    assert result.plan["field_specs"][0]["name"] == "title"
    assert result.plan["field_specs"][0]["clean_data_type"] == "text"


def test_compile_plan_uses_explicit_max_items_instead_of_default():
    request = CompilePlanRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com")),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item", max_items=13020)),
                WorkflowNode(
                    id="n3",
                    type="extract_field",
                    data=NodeData(fields=[{"name": "title", "selector": "h1"}]),
                ),
            ],
            edges=[
                WorkflowEdge(id="e1", source="n1", target="n2"),
                WorkflowEdge(id="e2", source="n2", target="n3"),
            ],
        )
    )
    result = compile_plan(request)
    assert result.success is True
    assert result.plan["limits"]["max_items"] == 13020


# ----------------------------------------------------------------------
# generate_crawler tests
# ----------------------------------------------------------------------

def test_generate_crawler_returns_domain_response():
    """generate_crawler returns GenerateCrawlerResponse, not JSONResponse."""
    request = GenerateCrawlerRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com")),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(id="n3", type="extract_field", data=NodeData(fields=[{"name": "title", "selector": "h1", "type": "text"}])),
            ],
            edges=[]
        )
    )
    # Note: This may fail if LLM is not configured, but it should return a domain response, not JSONResponse
    result = generate_crawler(request)
    assert hasattr(result, "success")  # It's a Pydantic model, not a JSONResponse
    # If LLM is not configured, success will be False but it's still a domain response
    if not result.success:
        assert result.error is not None


def test_generate_crawler_uses_prompt_override(monkeypatch):
    captured = {"user": ""}

    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            captured["user"] = user
            from llm_client import LLMResponse
            return LLMResponse(content="print('ok')", model="fake-model", usage={"prompt_tokens": 1, "completion_tokens": 1})

    monkeypatch.setattr("backend.workflow_services.get_default_client", lambda: FakeClient())

    request = GenerateCrawlerRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com")),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(id="n3", type="extract_field", data=NodeData(fields=[{"name": "title", "selector": "h1", "type": "text"}])),
            ],
            edges=[],
        ),
        prompt_override="Use robust retries and export newline-delimited JSON.",
    )

    result = generate_crawler(request)

    assert result.success is True
    assert result.editable_prompt == "Use robust retries and export newline-delimited JSON."
    assert "Use robust retries and export newline-delimited JSON." in captured["user"]
    assert "Execution Plan (Deterministic)" in captured["user"]


def test_generate_skeleton_returns_script_with_required_input():
    request = GenerateSkeletonRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com")),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(id="n3", type="extract_field", data=NodeData(fields=[{"name": "title", "selector": "h1"}])),
            ],
            edges=[
                WorkflowEdge(id="e1", source="n1", target="n2"),
                WorkflowEdge(id="e2", source="n2", target="n3"),
            ],
        )
    )
    result = generate_skeleton(request)
    assert result.success is True
    assert result.filename == "crawler_skeleton.py"
    assert "sync_playwright" in result.script


def test_format_script_normalizes_python_whitespace():
    response = format_script(FormatScriptRequest(content="def run():\r\n\treturn 1\r\n", language="python"))
    assert response.success is True
    assert response.formatted_content == "def run():\n    return 1\n"
    assert response.changed is True


def test_save_script_writes_inside_workspace(monkeypatch):
    workspace_root = make_test_workspace("service-save-script")
    monkeypatch.setattr("backend.workflow_services.WORKSPACE_ROOT", workspace_root)

    response = save_script(
        SaveScriptRequest(
            relative_path="generated/test_crawler.py",
            content="print('ok')",
        )
    )

    assert response.success is True
    assert response.created is True
    assert response.relative_path == "generated/test_crawler.py"
    assert (workspace_root / "generated" / "test_crawler.py").read_text(encoding="utf-8") == "print('ok')\n"


def test_save_script_rejects_outside_workspace(monkeypatch):
    workspace_root = make_test_workspace("service-save-script-outside")
    monkeypatch.setattr("backend.workflow_services.WORKSPACE_ROOT", workspace_root)

    with pytest.raises(ScriptPersistenceError) as exc_info:
        save_script(
            SaveScriptRequest(
                relative_path="../escape.py",
                content="print('bad')",
            )
        )

    assert exc_info.value.error_code == "path_outside_workspace"


# ----------------------------------------------------------------------
# Service layer must not import or use JSONResponse
# ----------------------------------------------------------------------

def test_service_module_does_not_use_json_response():
    """Verify that workflow_services.py does not import or construct JSONResponse."""
    import backend.workflow_services as services_module
    import inspect
    
    source = inspect.getsource(services_module)
    # Should not import JSONResponse (only mention in docstring is fine)
    # Check for actual import statement
    assert "from fastapi.responses import JSONResponse" not in source, \
        "Service layer should not import JSONResponse"
    assert "from fastapi import APIRouter" not in source, \
        "Service layer should not import FastAPI APIRouter"
    # Check for actual construction (not just docstring mention)
    lines_with_json_response = [
        line for line in source.split('\n')
        if 'JSONResponse' in line and not line.strip().startswith('#')
        and 'HTTP protocol handling' not in line
    ]
    assert not lines_with_json_response, \
        f"Service layer should not construct JSONResponse. Found: {lines_with_json_response}"


def test_clean_data_builds_prompt_and_returns_llm_response(monkeypatch):
    captured = {"prompt": ""}

    def fake_run(prompt: str):
        captured["prompt"] = prompt
        return AssistLlmResponse(success=True, result={"cleaned_value": 1234.56, "confidence": 0.9})

    monkeypatch.setattr("backend.assist_services._run_llm_json_task", fake_run)

    request = AssistCleanDataRequest(raw_data="$1,234.56", data_type="price")
    response = clean_data(request)

    assert response.success is True
    assert response.result["cleaned_value"] == 1234.56
    assert "$1,234.56" in captured["prompt"]
    assert "price" in captured["prompt"]

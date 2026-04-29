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
    assert "Selector Compatibility Contract" in result["prompt"]
    assert "Output Contract" in result["prompt"]
    assert "Execution Plan (Deterministic)" in result["effective_prompt"]
    assert "Output Strategy (In-Memory)" in result["effective_prompt"]


def test_graph_to_prompt_includes_html_and_field_samples():
    request = ToPromptRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com")),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(
                    id="n3",
                    type="extract_field",
                    data=NodeData(
                        html_fragment="<article class='item'><span class='price'>$12.34</span></article>",
                        fields=[
                            {
                                "name": "price",
                                "selector": ".price",
                                "type": "text",
                            }
                        ],
                    ),
                ),
            ],
            edges=[],
        )
    )

    result = graph_to_prompt(request)

    assert result["success"] is True
    assert "Page Evidence (HTML Sample)" in result["prompt"]
    assert "<article class='item'>" in result["prompt"]
    assert "`price` from `.price` as `text`" in result["prompt"]


def test_graph_to_prompt_strips_deprecated_max_steps_from_plan_and_prompt():
    request = ToPromptRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData.model_validate({"url": "http://example.com", "max_steps": 12})),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(id="n3", type="extract_field", data=NodeData(fields=[{"name": "title", "selector": "h1"}])),
            ],
            edges=[],
        )
    )

    result = graph_to_prompt(request)

    assert "max_steps" not in result["effective_prompt"]
    assert "max_steps" not in result["prompt"]
    assert "max_steps" not in result["plan"]["limits"]


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
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com")),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(
                    id="n3",
                    type="extract_field",
                    data=NodeData(fields=[{"name": "title", "selector": "h1", "type": "text"}]),
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
    assert "max_items" not in result.plan["limits"]
    assert result.plan["field_specs"][0]["name"] == "title"
    assert result.plan["field_specs"][0]["type"] == "text"


def test_compile_plan_removes_deprecated_max_items_limit():
    request = CompilePlanRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com")),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
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
    assert "max_items" not in result.plan["limits"]


def test_compile_plan_includes_emit_record_output_config():
    request = CompilePlanRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com")),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(id="n3", type="extract_field", data=NodeData(fields=[{"name": "title", "selector": "h1"}])),
                WorkflowNode(
                    id="n4",
                    type="emit_record",
                    data=NodeData(
                        output_mode="sqlite",
                        sqlite_path="output/products.db",
                        sqlite_table="products",
                        write_mode="upsert",
                        dedupe_keys=["detail_url"],
                        batch_size=25,
                    ),
                ),
            ],
            edges=[
                WorkflowEdge(id="e1", source="n1", target="n2"),
                WorkflowEdge(id="e2", source="n2", target="n3"),
                WorkflowEdge(id="e3", source="n3", target="n4"),
            ],
        )
    )

    result = compile_plan(request)

    assert result.success is True
    assert result.plan["output"] == {
        "mode": "sqlite",
        "json_file_path": "output/crawler_output.json",
        "sqlite_path": "output/products.db",
        "sqlite_table": "products",
        "write_mode": "upsert",
        "dedupe_keys": ["detail_url"],
        "batch_size": 25,
    }


def test_compile_plan_defaults_emit_record_to_memory_when_output_mode_unspecified():
    request = CompilePlanRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com")),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(id="n3", type="extract_field", data=NodeData(fields=[{"name": "title", "selector": "h1"}])),
                WorkflowNode(id="n4", type="emit_record", data=NodeData()),
            ],
            edges=[
                WorkflowEdge(id="e1", source="n1", target="n2"),
                WorkflowEdge(id="e2", source="n2", target="n3"),
                WorkflowEdge(id="e3", source="n3", target="n4"),
            ],
        )
    )

    result = compile_plan(request)

    assert result.success is True
    assert result.plan["output"] == {
        "mode": "memory",
        "json_file_path": "output/crawler_output.json",
        "sqlite_path": "output/crawler_output.db",
        "sqlite_table": "records",
        "write_mode": "append",
        "dedupe_keys": [],
        "batch_size": 50,
    }


# ----------------------------------------------------------------------
# generate_crawler tests
# ----------------------------------------------------------------------

def test_generate_crawler_returns_domain_response(monkeypatch):
    """generate_crawler returns GenerateCrawlerResponse, not JSONResponse."""
    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            from llm_client import LLMResponse
            if "principal reviewer" in system.lower():
                return LLMResponse(
                    content='{"approve": true, "summary": "looks good", "issues": [], "revision_instructions": []}',
                    model="fake-model",
                    usage={"prompt_tokens": 1, "completion_tokens": 1},
                )
            return LLMResponse(content="print('ok')", model="fake-model", usage={"prompt_tokens": 1, "completion_tokens": 1})

    monkeypatch.setattr("backend.workflows.generation_pipeline.get_default_client", lambda: FakeClient())

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
    result = generate_crawler(request)
    assert hasattr(result, "success")  # It's a Pydantic model, not a JSONResponse
    assert result.success is True
    assert result.generation_mode == "lite"
    assert result.review_summary is None


def test_generate_crawler_uses_prompt_override(monkeypatch):
    captured_calls = []

    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            from llm_client import LLMResponse
            captured_calls.append({"system": system, "user": user, "kwargs": kwargs})
            if "principal reviewer" in system.lower():
                return LLMResponse(
                    content='{"approve": true, "summary": "looks good", "issues": [], "revision_instructions": []}',
                    model="fake-model",
                    usage={"prompt_tokens": 1, "completion_tokens": 1},
                )
            return LLMResponse(content="print('ok')", model="fake-model", usage={"prompt_tokens": 1, "completion_tokens": 1})

    monkeypatch.setattr("backend.workflows.generation_pipeline.get_default_client", lambda: FakeClient())

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
    generation_prompt = captured_calls[0]["user"]

    assert result.success is True
    assert len(captured_calls) == 1
    assert captured_calls[0]["kwargs"]["request_name"] == "workflow_generate_crawler_draft"
    assert result.editable_prompt == "Use robust retries and export newline-delimited JSON."
    assert "Use robust retries and export newline-delimited JSON." in generation_prompt
    assert "max_tokens" not in captured_calls[0]["kwargs"]


def test_generate_crawler_strips_deprecated_max_steps_from_generation_prompt(monkeypatch):
    captured_calls = []

    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            from llm_client import LLMResponse
            captured_calls.append({"system": system, "user": user, "kwargs": kwargs})
            return LLMResponse(content="print('ok')", model="fake-model", usage={"prompt_tokens": 1, "completion_tokens": 1})

    monkeypatch.setattr("backend.workflows.generation_pipeline.get_default_client", lambda: FakeClient())

    request = GenerateCrawlerRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData.model_validate({"url": "http://example.com", "max_steps": 99})),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(id="n3", type="extract_field", data=NodeData(fields=[{"name": "title", "selector": "h1"}])),
            ],
            edges=[],
        )
    )

    result = generate_crawler(request)
    generation_prompt = captured_calls[0]["user"]

    assert result.success is True
    assert "max_steps" not in captured_calls[0]["user"]
    assert "Execution Plan (Deterministic)" in generation_prompt
    assert "Output Strategy (In-Memory)" in generation_prompt
    assert "Non-Negotiable Implementation Guardrails" in generation_prompt
    assert "Deterministic Skeleton (Reference Base)" in generation_prompt
    assert "sync_playwright" in generation_prompt


def test_generate_crawler_uses_sqlite_capable_skeleton_as_base(monkeypatch):
    captured_calls = []

    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            from llm_client import LLMResponse
            captured_calls.append({"system": system, "user": user})
            if "principal reviewer" in system.lower():
                return LLMResponse(
                    content='{"approve": true, "summary": "looks good", "issues": [], "revision_instructions": []}',
                    model="fake-model",
                    usage={"prompt_tokens": 1, "completion_tokens": 1},
                )
            return LLMResponse(content="print('ok')", model="fake-model", usage={"prompt_tokens": 1, "completion_tokens": 1})

    monkeypatch.setattr("backend.workflows.generation_pipeline.get_default_client", lambda: FakeClient())

    request = GenerateCrawlerRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com")),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(id="n3", type="extract_field", data=NodeData(fields=[{"name": "title", "selector": "h1"}])),
                WorkflowNode(
                    id="n4",
                    type="emit_record",
                    data=NodeData(
                        output_mode="sqlite",
                        sqlite_path="output/products.db",
                        sqlite_table="products",
                        write_mode="upsert",
                        dedupe_keys=["detail_url"],
                    ),
                ),
            ],
            edges=[],
        )
    )

    result = generate_crawler(request)
    generation_prompt = captured_calls[0]["user"]
    generation_system = captured_calls[0]["system"]

    assert result.success is True
    assert len(captured_calls) == 1
    assert "Output Strategy (SQLite)" in generation_prompt
    assert "Deterministic Skeleton (Reference Base)" in generation_prompt
    assert "OUTPUT_MODE = 'sqlite'" in generation_prompt
    assert "OUTPUT_SQLITE_PATH = 'output/products.db'" in generation_prompt
    assert "persist_sqlite_records" in generation_prompt
    assert "reference skeleton" in generation_system.lower()


def test_generate_crawler_revises_script_when_review_requests_changes(monkeypatch):
    class FakeClient:
        def __init__(self):
            self.calls = []

        def generate_with_system(self, system: str, user: str, **kwargs):
            from llm_client import LLMResponse
            self.calls.append({"system": system, "kwargs": kwargs})
            if "principal reviewer" in system.lower():
                return LLMResponse(
                    content=(
                        '{"approve": false, "summary": "needs persistence fix", '
                        '"issues": [{"severity": "high", "category": "output", "finding": "missing sqlite upsert", '
                        '"fix": "preserve sqlite persistence helper"}], '
                        '"revision_instructions": ["restore sqlite persistence helper and keep output contract"]}'
                    ),
                    model="fake-model",
                    usage={"prompt_tokens": 2, "completion_tokens": 2},
                )
            if "revise the provided crawler draft" in system.lower():
                return LLMResponse(
                    content="print('revised')",
                    model="fake-model",
                    usage={"prompt_tokens": 3, "completion_tokens": 3},
                )
            return LLMResponse(
                content="print('draft')",
                model="fake-model",
                usage={"prompt_tokens": 1, "completion_tokens": 1},
            )

    fake_client = FakeClient()
    monkeypatch.setattr("backend.workflows.generation_pipeline.get_default_client", lambda: fake_client)

    request = GenerateCrawlerRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com")),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(id="n3", type="extract_field", data=NodeData(fields=[{"name": "title", "selector": "h1"}])),
                WorkflowNode(
                    id="n4",
                    type="emit_record",
                    data=NodeData(output_mode="sqlite", sqlite_path="output/products.db", sqlite_table="products"),
                ),
            ],
            edges=[],
        ),
        generation_mode="pro",
    )

    result = generate_crawler(request)

    assert result.success is True
    assert result.script == "print('revised')"
    assert result.review_summary is not None
    assert result.review_summary["approve"] is False
    assert result.generation_mode == "pro"
    assert result.usage == {"prompt_tokens": 6, "completion_tokens": 6}
    assert len(fake_client.calls) == 3
    assert [call["kwargs"]["request_name"] for call in fake_client.calls] == [
        "workflow_generate_crawler_draft",
        "workflow_generate_crawler_review",
        "workflow_generate_crawler_revision",
    ]


def test_generate_crawler_reports_token_limit_warning_in_lite_mode(monkeypatch):
    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            from llm_client import LLMResponse
            return LLMResponse(
                content="print('truncated')",
                model="fake-model",
                usage={"prompt_tokens": 1, "completion_tokens": 1},
                finish_reason="length",
            )

    monkeypatch.setattr("backend.workflows.generation_pipeline.get_default_client", lambda: FakeClient())

    request = GenerateCrawlerRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com")),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(id="n3", type="extract_field", data=NodeData(fields=[{"name": "title", "selector": "h1"}])),
            ],
            edges=[],
        )
    )

    result = generate_crawler(request)

    assert result.success is True
    assert result.generation_mode == "lite"
    assert result.warnings == ["Draft generation reached the model token limit; the returned content may be truncated."]


def test_generate_crawler_fails_when_length_stop_returns_empty_script(monkeypatch):
    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            from llm_client import LLMResponse
            return LLMResponse(
                content="",
                model="fake-model",
                usage={"prompt_tokens": 1, "completion_tokens": 1},
                finish_reason="length",
            )

    monkeypatch.setattr("backend.workflows.generation_pipeline.get_default_client", lambda: FakeClient())

    request = GenerateCrawlerRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com")),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(id="n3", type="extract_field", data=NodeData(fields=[{"name": "title", "selector": "h1"}])),
            ],
            edges=[],
        )
    )

    result = generate_crawler(request)

    assert result.success is False
    assert result.error == "Draft generation returned empty content after hitting the model token limit."
    assert result.warnings == ["Draft generation reached the model token limit; the returned content may be truncated."]


def test_generate_crawler_rejects_elementhandle_locator_usage(monkeypatch):
    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            from llm_client import LLMResponse
            return LLMResponse(
                content="for item in items:\n    title = item.locator('.title').inner_text()\n",
                model="fake-model",
                usage={"prompt_tokens": 1, "completion_tokens": 1},
            )

    monkeypatch.setattr("backend.workflows.generation_pipeline.get_default_client", lambda: FakeClient())

    request = GenerateCrawlerRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com")),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(id="n3", type="extract_field", data=NodeData(fields=[{"name": "title", "selector": ".title"}])),
            ],
            edges=[],
        )
    )

    result = generate_crawler(request)

    assert result.success is False
    assert result.error == "Draft generation produced Playwright-incompatible ElementHandle locator usage."
    assert any("item.locator(...)" in warning for warning in result.warnings)


def test_generate_crawler_records_sandbox_failure(monkeypatch, tmp_path):
    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            from llm_client import LLMResponse
            return LLMResponse(
                content="raise RuntimeError('sandbox boom')",
                model="fake-model",
                usage={"prompt_tokens": 1, "completion_tokens": 1},
            )

    monkeypatch.setattr("backend.workflows.generation_pipeline.get_default_client", lambda: FakeClient())
    monkeypatch.setattr("backend.workflows.script_sandbox.SANDBOX_ROOT", tmp_path / "script-sandbox")

    request = GenerateCrawlerRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com")),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(id="n3", type="extract_field", data=NodeData(fields=[{"name": "title", "selector": "h1"}])),
            ],
            edges=[],
        ),
        run_sandbox=True,
    )

    result = generate_crawler(request)

    assert result.success is True
    assert result.sandbox_result is not None
    assert result.sandbox_result["success"] is False
    assert result.sandbox_result["exit_code"] != 0
    assert "sandbox boom" in result.sandbox_result["stderr_tail"]
    assert any("Script sandbox failed" in warning for warning in result.warnings)
    assert Path(result.sandbox_result["log_path"]).exists()
    assert "sandbox_completed" in Path(result.sandbox_result["log_path"]).read_text(encoding="utf-8")


def test_generate_crawler_can_skip_sandbox(monkeypatch):
    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            from llm_client import LLMResponse
            return LLMResponse(content="print('ok')", model="fake-model", usage={"prompt_tokens": 1, "completion_tokens": 1})

    monkeypatch.setattr("backend.workflows.generation_pipeline.get_default_client", lambda: FakeClient())

    request = GenerateCrawlerRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com")),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(id="n3", type="extract_field", data=NodeData(fields=[{"name": "title", "selector": "h1"}])),
            ],
            edges=[],
        ),
        run_sandbox=False,
    )

    result = generate_crawler(request)

    assert result.success is True
    assert result.sandbox_result is None
    assert not any(item.get("stage") == "script_sandbox" for item in result.generation_trace or [])


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


def test_generate_skeleton_embeds_sqlite_output_config():
    request = GenerateSkeletonRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com")),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(id="n3", type="extract_field", data=NodeData(fields=[{"name": "title", "selector": "h1"}])),
                WorkflowNode(
                    id="n4",
                    type="emit_record",
                    data=NodeData(
                        output_mode="sqlite",
                        sqlite_path="output/products.db",
                        sqlite_table="products",
                        write_mode="upsert",
                        dedupe_keys=["detail_url"],
                    ),
                ),
            ],
            edges=[
                WorkflowEdge(id="e1", source="n1", target="n2"),
                WorkflowEdge(id="e2", source="n2", target="n3"),
                WorkflowEdge(id="e3", source="n3", target="n4"),
            ],
        )
    )

    result = generate_skeleton(request)

    assert result.success is True
    assert "OUTPUT_MODE = 'sqlite'" in result.script
    assert "OUTPUT_SQLITE_PATH = 'output/products.db'" in result.script
    assert "OUTPUT_SQLITE_TABLE = 'products'" in result.script
    assert "DEDUPE_KEYS = [" in result.script
    assert "_identity_key" in result.script
    assert 'ON CONFLICT ({", ".join(quote_ident(column) for column in conflict_columns)})' in result.script


def test_generate_skeleton_strips_deprecated_max_steps_from_output():
    request = GenerateSkeletonRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData.model_validate({"url": "http://example.com", "max_steps": 99})),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(id="n3", type="extract_field", data=NodeData(fields=[{"name": "title", "selector": "h1"}])),
            ],
            edges=[],
        )
    )

    result = generate_skeleton(request)

    assert result.success is True
    assert "max_steps" not in result.script
    assert "max_steps" not in result.plan["limits"]


def test_generate_skeleton_uses_aligned_default_json_output_path():
    request = GenerateSkeletonRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com")),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(id="n3", type="extract_field", data=NodeData(fields=[{"name": "title", "selector": "h1"}])),
                WorkflowNode(id="n4", type="emit_record", data=NodeData()),
            ],
            edges=[
                WorkflowEdge(id="e1", source="n1", target="n2"),
                WorkflowEdge(id="e2", source="n2", target="n3"),
                WorkflowEdge(id="e3", source="n3", target="n4"),
            ],
        )
    )

    result = generate_skeleton(request)

    assert result.success is True
    assert "OUTPUT_JSON_FILE = 'output/crawler_output.json'" in result.script


def test_generate_skeleton_adapts_timeouts_for_sandbox_runs():
    request = GenerateSkeletonRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com")),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(id="n3", type="extract_field", data=NodeData(fields=[{"name": "title", "selector": "h1"}])),
            ],
            edges=[],
        )
    )

    result = generate_skeleton(request)

    assert result.success is True
    assert 'SANDBOX_HEADLESS = os.environ.get("CRAWLER_SANDBOX_MODE") == "1"' in result.script
    assert 'SANDBOX_TIMEOUT_SECONDS = int(os.environ.get("CRAWLER_SANDBOX_TIMEOUT_SECONDS", "0") or 0)' in result.script
    assert 'SANDBOX_DEADLINE = time.monotonic() + SANDBOX_TIMEOUT_SECONDS if SANDBOX_TIMEOUT_SECONDS > 0 else None' in result.script
    assert 'page.goto(ENTRY_URL, wait_until="domcontentloaded", timeout=remaining_timeout_ms(30000, reserve_seconds=5))' in result.script
    assert 'page.goto(ENTRY_URL, wait_until="load", timeout=remaining_timeout_ms(45000, reserve_seconds=2))' in result.script
    assert 'next_button.scroll_into_view_if_needed(timeout=remaining_timeout_ms(3000, reserve_seconds=3))' in result.script
    assert 'next_button.click(timeout=remaining_timeout_ms(5000, reserve_seconds=3))' in result.script
    assert 'page.wait_for_load_state("domcontentloaded", timeout=remaining_timeout_ms(10000, reserve_seconds=3))' in result.script


def test_generate_skeleton_clamps_timeouts_with_small_sandbox_budget(monkeypatch):
    request = GenerateSkeletonRequest(
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://example.com")),
                WorkflowNode(id="n2", type="select_list", data=NodeData(item_selector=".item")),
                WorkflowNode(id="n3", type="extract_field", data=NodeData(fields=[{"name": "title", "selector": "h1"}])),
            ],
            edges=[],
        )
    )
    monkeypatch.setenv("CRAWLER_SANDBOX_MODE", "1")
    monkeypatch.setenv("CRAWLER_SANDBOX_TIMEOUT_SECONDS", "5")

    result = generate_skeleton(request)
    namespace: dict[str, object] = {"__name__": "sandbox_probe"}
    exec(result.script, namespace)

    assert result.success is True
    remaining_timeout_ms = namespace["remaining_timeout_ms"]
    assert callable(remaining_timeout_ms)
    assert remaining_timeout_ms(30000, reserve_seconds=5) == 1
    assert 1 <= remaining_timeout_ms(45000, reserve_seconds=2) <= 3000
    assert 1 <= remaining_timeout_ms(10000, reserve_seconds=3) <= 2000


def test_format_script_normalizes_python_whitespace():
    response = format_script(FormatScriptRequest(content="def run():\r\n\treturn 1\r\n", language="python"))
    assert response.success is True
    assert response.formatted_content == "def run():\n    return 1\n"
    assert response.changed is True


def test_save_script_writes_inside_workspace(monkeypatch):
    workspace_root = make_test_workspace("service-save-script")
    monkeypatch.setattr("backend.workflows.script_artifacts.WORKSPACE_ROOT", workspace_root)

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
    monkeypatch.setattr("backend.workflows.script_artifacts.WORKSPACE_ROOT", workspace_root)

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

"""Regression tests for workflow services layer.

These tests verify that service functions:
1. Return domain results on success
2. Raise domain exceptions (not JSONResponse) on failure
"""

import pytest
from backend.workflow_schemas import (
    ValidateWorkflowRequest,
    WorkflowGraph,
    WorkflowNode,
    NodeData,
    FromLegacyConfigRequest,
    ToPromptRequest,
    GenerateCrawlerRequest,
)
from backend.workflow_services import (
    validate_graph,
    convert_legacy_config,
    graph_to_prompt,
    generate_crawler,
    WorkflowValidationError,
    WorkflowConversionError,
    PromptGenerationError,
)


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
            nodes=[WorkflowNode(id="n1", type="open_page", data=NodeData(url="http://a.com"))],
            edges=[
                WorkflowEdge(id="e1", source="n1", target="n2"),
                WorkflowEdge(id="e1", source="n2", target="n3"),
            ]
        )
    )
    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_graph(request)
    assert exc_info.value.error_code == "duplicate_edge_ids"


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

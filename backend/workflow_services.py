"""Workflow services - domain logic layer for workflow operations.

This module contains pure business logic without HTTP concerns.
HTTP protocol handling (JSONResponse construction) is handled by workflow_routes.py.
"""

import re
from dataclasses import dataclass

from llm_client import get_default_client, CRAWLER_SYSTEM_PROMPT
from prompts import CrawlerPromptGenerator

from .workflow_schemas import (
    FromLegacyConfigRequest,
    FromLegacyConfigResponse,
    NodeData,
    ToPromptRequest,
    ValidateWorkflowRequest,
    WorkflowEdge,
    WorkflowGraph,
    WorkflowNode,
    GenerateCrawlerRequest,
    GenerateCrawlerResponse,
)


# ----------------------------------------------------------------------
# Domain Exceptions - raised by service layer, caught by routes layer
# ----------------------------------------------------------------------


@dataclass
class WorkflowValidationError(Exception):
    """Raised when workflow validation fails."""
    error_code: str
    error: str

    def __str__(self):
        return f"{self.error_code}: {self.error}"


@dataclass
class WorkflowConversionError(Exception):
    """Raised when legacy config conversion fails."""
    error: str

    def __str__(self):
        return self.error


@dataclass
class PromptGenerationError(Exception):
    """Raised when prompt generation fails."""
    error: str

    def __str__(self):
        return self.error


def validate_graph(request: ValidateWorkflowRequest) -> dict:
    """Validate a workflow graph and return domain result.
    
    Raises WorkflowValidationError if validation fails.
    """
    graph = request.graph
    if not graph.nodes:
        raise WorkflowValidationError(
            error_code="workflow_empty",
            error="Workflow must have at least one node."
        )

    duplicate_node_ids = _find_duplicates(node.id for node in graph.nodes)
    if duplicate_node_ids:
        raise WorkflowValidationError(
            error_code="duplicate_node_ids",
            error=f"Workflow node ids must be unique: {', '.join(duplicate_node_ids)}."
        )

    duplicate_edge_ids = _find_duplicates(edge.id for edge in graph.edges)
    if duplicate_edge_ids:
        raise WorkflowValidationError(
            error_code="duplicate_edge_ids",
            error=f"Workflow edge ids must be unique: {', '.join(duplicate_edge_ids)}."
        )

    # MVP validation is intentionally structural: node/edge schemas, stable ids, and one entry node.
    # Unknown node types and dangling edges are left to runtime/test endpoints for now.
    entry_nodes = [node for node in graph.nodes if node.type == "open_page"]
    if not entry_nodes:
        raise WorkflowValidationError(
            error_code="entry_node_missing",
            error="Workflow must have an 'open_page' entry node."
        )
    if len(entry_nodes) > 1:
        raise WorkflowValidationError(
            error_code="entry_node_multiple",
            error="Workflow can only have one 'open_page' entry node."
        )

    return {"success": True, "message": "Workflow is valid"}


def _find_duplicates(values) -> list[str]:
    seen = set()
    duplicates = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def convert_legacy_config(request: FromLegacyConfigRequest) -> FromLegacyConfigResponse:
    """Convert a legacy config to a workflow DSL graph.
    
    Raises WorkflowConversionError if required fields are missing/blank.
    """
    if not request.url.strip() or not request.item_selector.strip():
        raise WorkflowConversionError(
            error="URL and item_selector are required for legacy conversion"
        )

    nodes = [
        WorkflowNode(
            id="node_1",
            type="open_page",
            data=NodeData(url=request.url),
        ),
        WorkflowNode(
            id="node_2",
            type="select_list",
            data=NodeData(item_selector=request.item_selector),
        ),
        WorkflowNode(
            id="node_3",
            type="extract_field",
            data=NodeData(fields=request.fields, html_fragment=request.html_fragment),
        ),
    ]
    edges = [
        WorkflowEdge(id="edge_1_2", source="node_1", target="node_2"),
        WorkflowEdge(id="edge_2_3", source="node_2", target="node_3"),
    ]

    if request.pagination_selector:
        nodes.append(
            WorkflowNode(
                id="node_4",
                type="paginate",
                data=NodeData(
                    pagination_selector=request.pagination_selector,
                    pagination_strategy=request.pagination_strategy,
                    max_pages=request.max_pages,
                ),
            )
        )
        edges.append(WorkflowEdge(id="edge_3_4", source="node_3", target="node_4"))

    return FromLegacyConfigResponse(
        success=True,
        graph=WorkflowGraph(nodes=nodes, edges=edges),
        warnings=[],
    )


def graph_to_prompt(request: ToPromptRequest) -> dict:
    """Convert a workflow graph to a prompt for LLM generation.
    
    Raises PromptGenerationError if required config is missing.
    """
    config = _extract_prompt_config(request.graph)
    if not config["url"] or not config["item_selector"]:
        raise PromptGenerationError(
            error="URL and item_selector are required to generate prompt"
        )

    prompt = CrawlerPromptGenerator().generate_from_simple_config(**config)
    return {"success": True, "prompt": prompt}


def _extract_prompt_config(graph: WorkflowGraph) -> dict:
    config = {
        "url": "",
        "item_selector": "",
        "fields": [],
        "pagination_selector": "",
        "pagination_strategy": "click_next",
        "max_pages": 50,
        "html_fragment": "",
    }

    for node in graph.nodes:
        data = node.data
        if node.type == "open_page":
            config["url"] = data.url or ""
        elif node.type == "select_list":
            config["item_selector"] = data.item_selector or ""
        elif node.type == "extract_field":
            config["fields"] = data.fields or []
            if data.html_fragment:
                config["html_fragment"] = data.html_fragment
        elif node.type == "paginate":
            config["pagination_selector"] = data.pagination_selector or ""
            if data.pagination_strategy:
                config["pagination_strategy"] = data.pagination_strategy
            if data.max_pages is not None:
                config["max_pages"] = data.max_pages

    return config


def generate_crawler(request: GenerateCrawlerRequest) -> GenerateCrawlerResponse:
    """Generate a Playwright crawler script from a DSL workflow graph.

    1. Extracts configuration from the graph nodes
    2. Generates a prompt using CrawlerPromptGenerator
    3. Calls LLM to generate the crawler script
    4. Returns {success, prompt, script, filename, model, usage} or error
    """
    config = _extract_prompt_config(request.graph)

    # Validate required inputs
    if not config["url"] or not config["item_selector"]:
        return GenerateCrawlerResponse(
            success=False,
            error="URL and item_selector are required to generate crawler script"
        )

    # Generate prompt
    prompt = CrawlerPromptGenerator().generate_from_simple_config(**config)

    # Call LLM
    try:
        client = get_default_client()
        response = client.generate_with_system(
            system=CRAWLER_SYSTEM_PROMPT,
            user=prompt
        )

        if response.error:
            return GenerateCrawlerResponse(
                success=False,
                error=response.error
            )

        # Extract filename from script content if present
        filename = "crawler.py"
        script_content = response.content
        # Try to find a filename like crawler_*.py in the content
        filename_match = re.search(r'crawler_\w+\.py', script_content)
        if filename_match:
            filename = filename_match.group(0)

        return GenerateCrawlerResponse(
            success=True,
            prompt=prompt,
            script=script_content,
            filename=filename,
            model=response.model,
            usage=response.usage,
        )
    except Exception as e:
        return GenerateCrawlerResponse(
            success=False,
            error=str(e)
        )

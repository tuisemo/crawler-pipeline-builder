from fastapi.responses import JSONResponse

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
)


def validate_graph(request: ValidateWorkflowRequest):
    graph = request.graph
    if not graph.nodes:
        return _validation_error("workflow_empty", "Workflow must have at least one node.")

    duplicate_node_ids = _find_duplicates(node.id for node in graph.nodes)
    if duplicate_node_ids:
        return _validation_error(
            "duplicate_node_ids",
            f"Workflow node ids must be unique: {', '.join(duplicate_node_ids)}.",
        )

    duplicate_edge_ids = _find_duplicates(edge.id for edge in graph.edges)
    if duplicate_edge_ids:
        return _validation_error(
            "duplicate_edge_ids",
            f"Workflow edge ids must be unique: {', '.join(duplicate_edge_ids)}.",
        )

    # MVP validation is intentionally structural: node/edge schemas, stable ids, and one entry node.
    # Unknown node types and dangling edges are left to runtime/test endpoints for now.
    entry_nodes = [node for node in graph.nodes if node.type == "open_page"]
    if not entry_nodes:
        return _validation_error("entry_node_missing", "Workflow must have an 'open_page' entry node.")
    if len(entry_nodes) > 1:
        return _validation_error("entry_node_multiple", "Workflow can only have one 'open_page' entry node.")

    return {"success": True, "message": "Workflow is valid"}


def _validation_error(error_code: str, error: str) -> JSONResponse:
    return JSONResponse({"success": False, "error_code": error_code, "error": error}, status_code=400)


def _find_duplicates(values) -> list[str]:
    seen = set()
    duplicates = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def convert_legacy_config(request: FromLegacyConfigRequest):
    if not request.url or not request.item_selector:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "URL and item_selector are required for legacy conversion"},
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


def graph_to_prompt(request: ToPromptRequest):
    config = _extract_prompt_config(request.graph)
    if not config["url"] or not config["item_selector"]:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "URL and item_selector are required to generate prompt"},
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

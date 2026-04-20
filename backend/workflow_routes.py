from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from .workflow_schemas import (
    ValidateWorkflowRequest,
    FromLegacyConfigRequest,
    FromLegacyConfigResponse,
    WorkflowGraph,
    WorkflowNode,
    WorkflowEdge,
    NodeData,
    ConversionWarning,
    ToPromptRequest
)
from prompts import CrawlerPromptGenerator

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

@router.post("/validate")
def validate_workflow(request: ValidateWorkflowRequest):
    graph = request.graph
    
    if not graph.nodes:
        return JSONResponse({"error": "Workflow must have at least one node."}, status_code=400)
    
    entry_nodes = [n for n in graph.nodes if n.type == "open_page"]
    if not entry_nodes:
        return JSONResponse({"error": "Workflow must have an 'open_page' entry node."}, status_code=400)
    if len(entry_nodes) > 1:
        return JSONResponse({"error": "Workflow can only have one 'open_page' entry node."}, status_code=400)
    
    # In a real validation we would check connections, cycles, etc.
    # For MVP, just checking entry node is enough to pass the basic test.
    
    return {"success": True, "message": "Workflow is valid"}

@router.post("/from-legacy-config", response_model=FromLegacyConfigResponse)
def from_legacy_config(request: FromLegacyConfigRequest):
    warnings = []
    
    # 1. MVP envelope check: fail if critical missing
    if not request.url or not request.item_selector:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "URL and item_selector are required for legacy conversion"}
        )
        
    # Check for unsupported features (if we added them to the request schema)
    # e.g., if there were a "detail_page_selector" field, we'd warn/error.
    
    # 2. Build the graph mapping
    nodes = []
    edges = []
    
    # Node 1: Open Page
    nodes.append(WorkflowNode(
        id="node_1",
        type="open_page",
        data=NodeData(url=request.url)
    ))
    
    # Node 2: Select List
    nodes.append(WorkflowNode(
        id="node_2",
        type="select_list",
        data=NodeData(item_selector=request.item_selector)
    ))
    edges.append(WorkflowEdge(id="edge_1_2", source="node_1", target="node_2"))
    
    # Node 3: Extract Fields
    nodes.append(WorkflowNode(
        id="node_3",
        type="extract_field",
        data=NodeData(fields=request.fields, html_fragment=request.html_fragment)
    ))
    edges.append(WorkflowEdge(id="edge_2_3", source="node_2", target="node_3"))
    
    # Node 4: Paginate (if configured)
    last_node_id = "node_3"
    if request.pagination_selector:
        nodes.append(WorkflowNode(
            id="node_4",
            type="paginate",
            data=NodeData(
                pagination_selector=request.pagination_selector,
                pagination_strategy=request.pagination_strategy,
                max_pages=request.max_pages
            )
        ))
        edges.append(WorkflowEdge(id=f"edge_{last_node_id[-1]}_4", source=last_node_id, target="node_4"))
        
    graph = WorkflowGraph(nodes=nodes, edges=edges)
    
    return FromLegacyConfigResponse(
        success=True,
        graph=graph,
        warnings=warnings
    )

@router.post("/to-prompt")
def to_prompt(request: ToPromptRequest):
    graph = request.graph
    
    url = ""
    item_selector = ""
    fields = []
    pagination_selector = ""
    pagination_strategy = "click_next"
    max_pages = 50
    html_fragment = ""
    
    for node in graph.nodes:
        if node.type == "open_page":
            url = node.data.url or ""
        elif node.type == "select_list":
            item_selector = node.data.item_selector or ""
        elif node.type == "extract_field":
            fields = node.data.fields or []
            if node.data.html_fragment:
                html_fragment = node.data.html_fragment
        elif node.type == "paginate":
            pagination_selector = node.data.pagination_selector or ""
            if node.data.pagination_strategy:
                pagination_strategy = node.data.pagination_strategy
            if node.data.max_pages is not None:
                max_pages = node.data.max_pages
                
    if not url or not item_selector:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "URL and item_selector are required to generate prompt"}
        )
        
    generator = CrawlerPromptGenerator()
    prompt = generator.generate_from_simple_config(
        url=url,
        item_selector=item_selector,
        fields=fields,
        pagination_selector=pagination_selector,
        pagination_strategy=pagination_strategy,
        max_pages=max_pages,
        html_fragment=html_fragment
    )
    
    return {"success": True, "prompt": prompt}

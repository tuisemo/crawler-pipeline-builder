from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal

class NodeData(BaseModel):
    # This matches the legacy config fields to be mapped to node properties
    url: Optional[str] = None
    item_selector: Optional[str] = None
    fields: Optional[List[Dict[str, Any]]] = None
    pagination_selector: Optional[str] = None
    pagination_strategy: Optional[str] = None
    max_pages: Optional[int] = None
    html_fragment: Optional[str] = None

class WorkflowNode(BaseModel):
    id: str
    type: str # e.g. "open_page", "select_list", "extract_field", "paginate"
    data: NodeData
    
class WorkflowEdge(BaseModel):
    id: str
    source: str
    target: str
    
class WorkflowGraph(BaseModel):
    nodes: List[WorkflowNode]
    edges: List[WorkflowEdge]

class ValidateWorkflowRequest(BaseModel):
    graph: WorkflowGraph

class ConversionWarning(BaseModel):
    message: str

class FromLegacyConfigRequest(BaseModel):
    url: str
    item_selector: str
    fields: List[Dict[str, Any]]
    pagination_selector: str = ""
    pagination_strategy: str = "click_next"
    max_pages: int = 50
    html_fragment: str = ""
    # Any other unsupported fields would trigger warnings
    
class FromLegacyConfigResponse(BaseModel):
    success: bool
    graph: Optional[WorkflowGraph] = None
    warnings: List[ConversionWarning] = []
    error: Optional[str] = None

class ToPromptRequest(BaseModel):
    graph: WorkflowGraph

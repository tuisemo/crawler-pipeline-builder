from pydantic import BaseModel, ConfigDict, StrictStr
from typing import List, Dict, Any, Optional
from enum import Enum

class NodeData(BaseModel):
    """MVP node data keeps legacy-compatible fields optional by design."""

    model_config = ConfigDict(extra="allow")

    url: Optional[str] = None
    item_selector: Optional[str] = None
    fields: Optional[List[Dict[str, Any]]] = None
    pagination_selector: Optional[str] = None
    pagination_strategy: Optional[str] = None
    max_pages: Optional[int] = None
    html_fragment: Optional[str] = None
    max_items: Optional[int] = None
    max_steps: Optional[int] = None

class WorkflowNode(BaseModel):
    id: StrictStr
    type: StrictStr # e.g. "open_page", "select_list", "extract_field", "paginate"
    data: NodeData

class WorkflowEdge(BaseModel):
    id: StrictStr
    source: StrictStr
    target: StrictStr

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

# Execution result schemas
class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

class ExecutionLog(BaseModel):
    timestamp: float
    level: LogLevel
    node_id: Optional[str] = None
    message: str
    details: Optional[Dict[str, Any]] = None

class NodeResult(BaseModel):
    node_id: str
    node_type: str
    success: bool
    started_at: float
    completed_at: float
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    logs: List[ExecutionLog] = []

class TestNodeRequest(BaseModel):
    graph: WorkflowGraph
    node_id: str
    session_id: Optional[str] = None
    # Execution limits
    max_items: int = 10
    max_steps: int = 100

class TestNodeResponse(BaseModel):
    success: bool
    node_id: str
    result: NodeResult
    logs: List[ExecutionLog] = []
    error: Optional[str] = None
    session_expired: bool = False

class SubflowBoundary(BaseModel):
    start_node_id: Optional[str] = None
    end_node_id: Optional[str] = None
    max_pages: Optional[int] = None
    max_items: Optional[int] = None
    max_steps: Optional[int] = None

class TestSubflowRequest(BaseModel):
    graph: WorkflowGraph
    boundary: Optional[SubflowBoundary] = None
    session_id: Optional[str] = None

class TestSubflowResponse(BaseModel):
    success: bool
    partial: bool = False
    node_results: List[NodeResult] = []
    logs: List[ExecutionLog] = []
    records: List[Dict[str, Any]] = []
    error: Optional[str] = None
    session_expired: bool = False
    steps_executed: int = 0


class GenerateCrawlerRequest(BaseModel):
    """Request to generate a Playwright crawler script from a DSL workflow graph."""
    graph: WorkflowGraph


class GenerateCrawlerResponse(BaseModel):
    """Response containing the generated crawler script and metadata."""
    success: bool
    prompt: Optional[str] = None
    script: Optional[str] = None
    filename: Optional[str] = None
    model: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    error: Optional[str] = None

from pydantic import BaseModel, ConfigDict, StrictStr, field_validator
from typing import List, Dict, Any, Optional, Annotated
from enum import Enum


# ----------------------------------------------------------------------
# Field extraction schema (used by extract_field)
# ----------------------------------------------------------------------


class FieldSchema(BaseModel):
    """Strongly-typed field definition for extract_field nodes.

    Supports legacy-compatible field shapes so that FromLegacyConfigRequest.fields
    and DSL extract_field.fields use the same schema. At minimum, each field needs
    a name and a selector; the extraction_type defaults to "text" if not provided.
    """

    model_config = ConfigDict(extra="allow")

    # Preferred names
    name: Optional[str] = None
    selector: Optional[str] = None
    type: Optional[str] = None

    # Legacy aliases (field_name, css, extraction_type)
    field_name: Optional[str] = None
    css: Optional[str] = None
    extraction_type: Optional[str] = None

    @field_validator("name", "field_name")
    @classmethod
    def _coerce_blank_to_none(cls, v: Optional[str]) -> Optional[str]:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    def resolved_name(self) -> Optional[str]:
        return self.name or self.field_name

    def resolved_selector(self) -> Optional[str]:
        return self.selector or self.css

    def resolved_type(self) -> Optional[str]:
        return self.type or self.extraction_type or "text"


# ----------------------------------------------------------------------
# Node-level data models (one per core node type)
# ----------------------------------------------------------------------


class OpenPageData(BaseModel):
    """Data model for open_page nodes. URL is required at validation time."""

    model_config = ConfigDict(extra="allow")

    url: str = ""  # Required; empty string triggers validation error
    max_steps: Optional[int] = None
    max_items: Optional[int] = None


class SelectListData(BaseModel):
    """Data model for select_list nodes. item_selector is required at validation time."""

    model_config = ConfigDict(extra="allow")

    item_selector: str = ""  # Required; empty string triggers validation error
    max_items: Optional[int] = None


class ExtractFieldData(BaseModel):
    """Data model for extract_field nodes. fields list is required at validation time."""

    model_config = ConfigDict(extra="allow")

    fields: Optional[List[Dict[str, Any]]] = None  # Replaced by strong FieldSchema in validate
    html_fragment: Optional[str] = None
    max_items: Optional[int] = None


class PaginateData(BaseModel):
    """Data model for paginate nodes. pagination_selector is required at validation time."""

    model_config = ConfigDict(extra="allow")

    pagination_selector: str = ""  # Required; empty string triggers validation error
    pagination_strategy: Optional[str] = None
    max_pages: Optional[int] = None


# ----------------------------------------------------------------------
# Legacy-compatible NodeData (still used by WorkflowNode for backward compatibility)
# ----------------------------------------------------------------------


class NodeData(BaseModel):
    """MVP node data keeps legacy-compatible fields optional by design.

    This class is preserved for backward compatibility with the existing
    WorkflowNode model. New validation code should use the dedicated
    data models (OpenPageData, SelectListData, ExtractFieldData, PaginateData)
    and call `validate_node_data` below.
    """

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


# ----------------------------------------------------------------------
# Node / Edge / Graph
# ----------------------------------------------------------------------


class WorkflowNode(BaseModel):
    id: StrictStr
    type: StrictStr  # e.g. "open_page", "select_list", "extract_field", "paginate"
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

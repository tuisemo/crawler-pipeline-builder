from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator
from typing import List, Dict, Any, Optional
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

    @field_validator("name", "field_name", "selector", "css")
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


class SelectListData(BaseModel):
    """Data model for select_list nodes. item_selector is required at validation time."""

    model_config = ConfigDict(extra="allow")

    item_selector: str = ""  # Required; empty string triggers validation error


class ExtractFieldData(BaseModel):
    """Data model for extract_field nodes. fields list is required at validation time."""

    model_config = ConfigDict(extra="allow")

    fields: Optional[List[FieldSchema]] = None
    html_fragment: Optional[str] = None


class PaginateData(BaseModel):
    """Data model for paginate nodes. pagination_selector is required at validation time."""

    model_config = ConfigDict(extra="allow")

    pagination_selector: str = ""  # Required; empty string triggers validation error
    pagination_strategy: Optional[str] = None
    max_pages: Optional[int] = None


class LoopData(BaseModel):
    """Data model for loop nodes.

    Consumes the item set produced by a upstream select_list and provides
    current-item context for downstream nodes.
    """

    model_config = ConfigDict(extra="allow")

    # on_error: "skip" (default) | "stop" - controls per-item failure behavior
    on_error: Optional[str] = None


class ConditionData(BaseModel):
    """Data model for condition nodes.

    Evaluates a simple expression against the current execution state
    and routes to either the true or false branch.
    """

    model_config = ConfigDict(extra="allow")

    condition: str = ""  # Required; empty string triggers validation error
    # expression_mode: "simple" (default) - whitelist of operators only
    expression_mode: Optional[str] = None


class EndData(BaseModel):
    """Data model for end nodes.

    Marks the explicit termination of a workflow path. It is a safe no-op
    in the executor (execution stops when ctx.state["ended"] is True).
    """

    model_config = ConfigDict(extra="allow")

    label: Optional[str] = None


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
    condition: Optional[str] = None
    expression_mode: Optional[str] = None
    on_error: Optional[str] = None
    label: Optional[str] = None
    output_mode: Optional[str] = None
    json_file_path: Optional[str] = None
    sqlite_path: Optional[str] = None
    sqlite_table: Optional[str] = None
    write_mode: Optional[str] = None
    dedupe_keys: Optional[List[str]] = None
    batch_size: Optional[int] = None


# ----------------------------------------------------------------------
# Node / Edge / Graph
# ----------------------------------------------------------------------


class WorkflowNode(BaseModel):
    id: StrictStr
    type: StrictStr  # e.g. "open_page", "select_list", "extract_field", "paginate"
    data: NodeData


class WorkflowEdge(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: StrictStr
    source: StrictStr
    target: StrictStr
    # Optional branch metadata for condition nodes.
    # Allowed values: true/false (bool) or "true"/"false"/"default".
    branch: Optional[str | bool] = None
    label: Optional[str] = None
    order: Optional[int] = None


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
    prompt_override: Optional[str] = None
    generation_mode: Optional[str] = "lite"
    run_sandbox: Optional[bool] = None
    sandbox_timeout_seconds: Optional[int] = None


class GenerateCrawlerResponse(BaseModel):
    """Response containing the generated crawler script and metadata."""
    success: bool
    prompt: Optional[str] = None
    editable_prompt: Optional[str] = None
    script: Optional[str] = None
    filename: Optional[str] = None
    model: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    generation_mode: Optional[str] = None
    generation_trace: Optional[List[Dict[str, Any]]] = None
    sandbox_result: Optional[Dict[str, Any]] = None
    warnings: List[str] = []
    review_summary: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class DetailBatchRunnerDatabaseConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    database_type: str = Field(default="sqlite", alias="type")
    path: str
    list_table_name: str = "records"
    record_id_field: str = "record_id"
    detail_url_field: str = "detail_url"
    source_url_field: Optional[str] = "source_url"
    title_field: Optional[str] = "title"


class DetailBatchRunnerTaskConfig(BaseModel):
    table_name: str = "detail_collection_tasks"
    status_values: List[str] = [
        "pending",
        "running",
        "succeeded",
        "failed_retryable",
        "failed_terminal",
        "skipped",
    ]
    max_attempts: int = 3


class DetailBatchRunnerCliConfig(BaseModel):
    executable: str = "page-extractor"
    command_prefix: Optional[List[str]] = None
    subcommand: str = "collect"
    output_root: str = "./detail-output"
    stdout_format: str = "json"
    exit_code_policy: str = "0_success_nonzero_failure"


class DetailBatchRunnerExecutionPolicy(BaseModel):
    default_concurrency: int = 4
    default_batch_size: int = 20
    subprocess_timeout_seconds: int = 180
    support_dry_run: bool = True
    support_limit: bool = True


class DetailBatchRunnerGenerationPolicy(BaseModel):
    language: str = "python"
    mode: str = "skeleton_enhancement"


class GeneratedScriptValidationCheck(BaseModel):
    name: str
    passed: bool
    detail: Optional[str] = None


class GeneratedScriptValidationResult(BaseModel):
    passed: bool
    checks: List[GeneratedScriptValidationCheck] = []
    errors: List[str] = []
    warnings: List[str] = []


class GenerateDetailBatchRunnerRequest(BaseModel):
    database: DetailBatchRunnerDatabaseConfig
    detail_task: DetailBatchRunnerTaskConfig = DetailBatchRunnerTaskConfig()
    detail_cli: DetailBatchRunnerCliConfig = DetailBatchRunnerCliConfig()
    execution_policy: DetailBatchRunnerExecutionPolicy = DetailBatchRunnerExecutionPolicy()
    generation_policy: DetailBatchRunnerGenerationPolicy = DetailBatchRunnerGenerationPolicy()
    prompt_override: Optional[str] = None


class GenerateDetailBatchRunnerResponse(BaseModel):
    success: bool
    prompt: Optional[str] = None
    script: Optional[str] = None
    filename: Optional[str] = None
    model: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    generation_mode: Optional[str] = None
    generation_trace: Optional[List[Dict[str, Any]]] = None
    warnings: List[str] = []
    validation: Optional[GeneratedScriptValidationResult] = None
    error: Optional[str] = None


class RunScriptSandboxRequest(BaseModel):
    """Manually execute a generated or edited crawler script in the sandbox."""

    script: str
    filename: Optional[str] = "crawler.py"
    timeout_seconds: Optional[int] = None


class RunScriptSandboxResponse(BaseModel):
    success: bool
    sandbox_result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class FormatScriptRequest(BaseModel):
    """Format a generated crawler script for easier editing."""

    content: str
    language: str = "python"


class FormatScriptResponse(BaseModel):
    success: bool
    formatted_content: Optional[str] = None
    changed: bool = False
    formatter: Optional[str] = None
    warnings: List[str] = []
    error: Optional[str] = None


class SaveScriptRequest(BaseModel):
    """Persist a generated or edited crawler script into the project workspace."""

    relative_path: str
    content: str
    overwrite: bool = False


class SaveScriptResponse(BaseModel):
    success: bool
    relative_path: Optional[str] = None
    absolute_path: Optional[str] = None
    bytes_written: int = 0
    created: bool = False
    overwritten: bool = False
    error: Optional[str] = None


class GenerateSkeletonRequest(BaseModel):
    """Request to generate deterministic crawler skeleton script from workflow graph."""
    graph: WorkflowGraph


class GenerateSkeletonResponse(BaseModel):
    """Response containing generated deterministic crawler skeleton."""
    success: bool
    script: Optional[str] = None
    filename: Optional[str] = None
    plan: Optional[Dict[str, Any]] = None
    warnings: List[str] = []
    error: Optional[str] = None


class CompilePlanRequest(BaseModel):
    """Request to compile a WorkflowGraph into a deterministic execution plan."""
    graph: WorkflowGraph


class CompilePlanResponse(BaseModel):
    """Response containing the compiled execution plan."""
    success: bool
    plan: Optional[Dict[str, Any]] = None
    warnings: List[str] = []
    error: Optional[str] = None


class AutoDetectRequest(BaseModel):
    """Run list/pagination auto-detection on the active browser page."""
    session_id: Optional[str] = None
    url: Optional[str] = None


class AutoDetectResponse(BaseModel):
    success: bool
    session_id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class AssistHtmlExtractRequest(BaseModel):
    """Extract cleaned HTML fragments for a target item selector."""
    item_selector: str
    session_id: Optional[str] = None
    url: Optional[str] = None
    max_items: int = 3
    include_pagination: bool = False


class AssistHtmlExtractResponse(BaseModel):
    success: bool
    session_id: Optional[str] = None
    html_fragment: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class AssistSelectorTestRequest(BaseModel):
    """Validate a selector against the current browser page and temporarily highlight matches."""

    selector: str
    session_id: Optional[str] = None
    url: Optional[str] = None
    clear_after_ms: int = 2200
    max_samples: int = 5


class AssistSelectorTestResponse(BaseModel):
    success: bool
    session_id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class AssistLlmRequest(BaseModel):
    """Generic request used by infer-fields / optimize-selector / analyze-pagination."""
    html_fragment: str
    session_id: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    initial_selector: Optional[str] = None


class AssistLlmResponse(BaseModel):
    success: bool
    result: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    reason: Optional[str] = None
    model: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    raw: Optional[str] = None
    warnings: List[str] = []
    error: Optional[str] = None

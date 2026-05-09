from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator
from typing import List, Dict, Any, Optional


# ----------------------------------------------------------------------
# Field extraction schema (used by extract_field)
# ----------------------------------------------------------------------


class FieldSchema(BaseModel):
    """Strongly-typed canonical field definition for extract_field nodes."""

    model_config = ConfigDict(extra="allow")

    # Preferred names
    name: Optional[str] = None
    selector: Optional[str] = None
    type: Optional[str] = None

    @field_validator("name", "selector")
    @classmethod
    def _coerce_blank_to_none(cls, v: Optional[str]) -> Optional[str]:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    def resolved_name(self) -> Optional[str]:
        return self.name

    def resolved_selector(self) -> Optional[str]:
        return self.selector

    def resolved_type(self) -> Optional[str]:
        return self.type or "text"


DEPRECATED_EXTRACTION_FIELD_KEYS = {"sample_value", "clean_data_type", "normalized_sample"}
FIELD_ALIAS_KEYS = {"field_name", "css", "extraction_type"}
FIELD_CANONICAL_KEYS = {"name", "selector", "type"}
REMOVED_FIELD_KEYS = DEPRECATED_EXTRACTION_FIELD_KEYS | FIELD_ALIAS_KEYS | FIELD_CANONICAL_KEYS


class LegacyFieldAliasError(ValueError):
    """Raised when removed legacy field aliases are still provided."""


def normalize_field_payload(raw_field: Any, index: int | None = None) -> dict[str, Any]:
    if isinstance(raw_field, dict):
        legacy_aliases = sorted(key for key in FIELD_ALIAS_KEYS if key in raw_field)
        if legacy_aliases:
            raise LegacyFieldAliasError(
                "Legacy field aliases are no longer supported: "
                f"{', '.join(legacy_aliases)}. Use name, selector, and type."
            )
    field = raw_field if isinstance(raw_field, FieldSchema) else FieldSchema.model_validate(raw_field)
    normalized: dict[str, Any] = {}
    if isinstance(raw_field, dict):
        normalized = {
            key: value
            for key, value in raw_field.items()
            if key not in REMOVED_FIELD_KEYS
        }

    name = field.resolved_name()
    if not name and index is not None:
        name = f"field_{index + 1}"
    if name:
        normalized["name"] = name

    selector = field.resolved_selector()
    if selector:
        normalized["selector"] = selector

    normalized["type"] = field.resolved_type() or "text"
    return normalized


def normalize_field_payloads(fields: List[Any] | None, assign_fallback_names: bool = False) -> List[Any] | None:
    if fields is None:
        return None

    normalized: list[dict[str, Any]] = []
    for index, raw_field in enumerate(fields):
        if isinstance(raw_field, dict):
            normalized.append(
                normalize_field_payload(
                    raw_field,
                    index=index if assign_fallback_names else None,
                )
            )
            continue
        normalized.append(raw_field)
    return normalized


# ----------------------------------------------------------------------
# Legacy-compatible NodeData (used by WorkflowNode)
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


class AssistLlmRequest(BaseModel):
    """Generic request used by infer-fields / optimize-selector / analyze-pagination."""
    html_fragment: str
    pruned_body_html: Optional[str] = None
    pagination_component_html: Optional[str] = None
    initial_selector: Optional[str] = None
    user_intent: Optional[str] = None


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

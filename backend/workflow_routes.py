from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .workflow_executor import executor
from .workflow_schemas import (
    FromLegacyConfigRequest,
    FromLegacyConfigResponse,
    FormatScriptRequest,
    FormatScriptResponse,
    GenerateCrawlerRequest,
    GenerateCrawlerResponse,
    SaveScriptRequest,
    SaveScriptResponse,
    TestNodeRequest,
    TestNodeResponse,
    TestSubflowRequest,
    TestSubflowResponse,
    ToPromptRequest,
    ValidateWorkflowRequest,
    CompilePlanRequest,
    CompilePlanResponse,
    GenerateSkeletonRequest,
    GenerateSkeletonResponse,
)
from .workflow_services import (
    compile_plan,
    convert_legacy_config,
    format_script,
    generate_skeleton,
    generate_crawler,
    graph_to_prompt,
    save_script,
    validate_graph,
    WorkflowValidationError,
    WorkflowConversionError,
    PromptGenerationError,
    ScriptFormattingError,
    ScriptPersistenceError,
)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.post("/validate")
def validate_workflow(request: ValidateWorkflowRequest):
    """Validate a workflow DSL graph."""
    try:
        return validate_graph(request)
    except WorkflowValidationError as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error_code": e.error_code, "error": e.error}
        )

@router.post(
    "/from-legacy-config",
    response_model=FromLegacyConfigResponse,
    response_model_exclude_none=True,
)
def from_legacy_config(request: FromLegacyConfigRequest):
    """Convert a legacy config to a workflow DSL graph."""
    try:
        return convert_legacy_config(request)
    except WorkflowConversionError as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(e)}
        )

@router.post("/to-prompt")
def to_prompt(request: ToPromptRequest):
    """Convert a workflow DSL graph to a prompt for LLM generation."""
    try:
        return graph_to_prompt(request)
    except PromptGenerationError as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(e)}
        )


@router.post("/compile-plan", response_model=CompilePlanResponse)
def compile_plan_endpoint(request: CompilePlanRequest):
    """Compile a workflow DSL graph into a deterministic execution plan."""
    return compile_plan(request)


@router.post("/generate-skeleton", response_model=GenerateSkeletonResponse)
def generate_skeleton_endpoint(request: GenerateSkeletonRequest):
    """Generate deterministic crawler skeleton without invoking LLM."""
    return generate_skeleton(request)


@router.post("/generate-crawler", response_model=GenerateCrawlerResponse)
def generate_crawler_endpoint(request: GenerateCrawlerRequest):
    """Generate a Playwright crawler script from a DSL workflow graph.

    This endpoint:
    1. Receives a WorkflowGraph (nodes + edges)
    2. Calls existing CrawlerPromptGenerator to generate prompt
    3. Calls LLM via llm_client.py to generate the crawler script
    4. Returns {success, prompt, script, filename, model, usage} or error
    """
    return generate_crawler(request)


@router.post("/format-script", response_model=FormatScriptResponse)
def format_script_endpoint(request: FormatScriptRequest):
    """Format generated script content for the editor workspace."""
    try:
        return format_script(request)
    except ScriptFormattingError as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(e)}
        )


@router.post("/save-script", response_model=SaveScriptResponse)
def save_script_endpoint(request: SaveScriptRequest):
    """Save generated or edited script content into the project workspace."""
    try:
        return save_script(request)
    except ScriptPersistenceError as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error_code": e.error_code, "error": e.error}
        )


@router.post("/test-node")
async def test_node(request: TestNodeRequest) -> TestNodeResponse:
    """Test a single workflow node with minimal prerequisites.
    
    This endpoint executes only the requested node and its necessary
    prerequisites, without committing downstream workflow side effects.
    Returns structured logs and node results for inspection.
    """
    return await executor.test_node(request)


@router.post("/test-subflow")
async def test_subflow(request: TestSubflowRequest) -> TestSubflowResponse:
    """Test a workflow subflow within graph boundaries.
    
    This endpoint executes nodes within the specified subflow boundaries,
    respecting execution limits (max_items, max_pages, max_steps).
    Returns structured logs, node results, and sample records.
    Partial-run failures preserve inspectable outputs.
    """
    return await executor.test_subflow(request)

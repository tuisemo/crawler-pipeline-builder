"""AI assist API routes."""

from fastapi import APIRouter

from .core.api_response import api_response
from .async_bridge import run_blocking
from .assist_services import (
    analyze_pagination,
    auto_detect,
    clean_data,
    extract_html_fragment,
    infer_fields,
    optimize_selector,
)
from .workflow_schemas import (
    AssistCleanDataRequest,
    AssistHtmlExtractRequest,
    AssistLlmRequest,
    AutoDetectRequest,
)

router = APIRouter(prefix="/api/assist", tags=["assist"])


@router.post("/auto-detect")
async def auto_detect_endpoint(request: AutoDetectRequest):
    return api_response(await run_blocking(lambda: auto_detect(request)))


@router.post("/extract-html")
async def extract_html_endpoint(request: AssistHtmlExtractRequest):
    return api_response(await run_blocking(lambda: extract_html_fragment(request)))


@router.post("/infer-fields")
def infer_fields_endpoint(request: AssistLlmRequest):
    response = infer_fields(request)
    if not response.success:
        return api_response(response, status_code=400)
    return api_response(response)


@router.post("/optimize-selector")
def optimize_selector_endpoint(request: AssistLlmRequest):
    response = optimize_selector(request)
    if not response.success:
        return api_response(response, status_code=400)
    return api_response(response)


@router.post("/analyze-pagination")
def analyze_pagination_endpoint(request: AssistLlmRequest):
    response = analyze_pagination(request)
    if not response.success:
        return api_response(response, status_code=400)
    return api_response(response)


@router.post("/clean-data")
def clean_data_endpoint(request: AssistCleanDataRequest):
    response = clean_data(request)
    if not response.success:
        return api_response(response, status_code=400)
    return api_response(response)

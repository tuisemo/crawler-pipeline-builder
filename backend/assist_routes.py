"""AI assist API routes."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

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
    AssistHtmlExtractResponse,
    AssistLlmRequest,
    AssistLlmResponse,
    AutoDetectRequest,
    AutoDetectResponse,
)

router = APIRouter(prefix="/api/assist", tags=["assist"])


@router.post("/auto-detect", response_model=AutoDetectResponse)
def auto_detect_endpoint(request: AutoDetectRequest):
    return auto_detect(request)


@router.post("/extract-html", response_model=AssistHtmlExtractResponse)
def extract_html_endpoint(request: AssistHtmlExtractRequest):
    return extract_html_fragment(request)


@router.post("/infer-fields", response_model=AssistLlmResponse)
def infer_fields_endpoint(request: AssistLlmRequest):
    response = infer_fields(request)
    if not response.success:
        return JSONResponse(status_code=400, content=response.model_dump())
    return response


@router.post("/optimize-selector", response_model=AssistLlmResponse)
def optimize_selector_endpoint(request: AssistLlmRequest):
    response = optimize_selector(request)
    if not response.success:
        return JSONResponse(status_code=400, content=response.model_dump())
    return response


@router.post("/analyze-pagination", response_model=AssistLlmResponse)
def analyze_pagination_endpoint(request: AssistLlmRequest):
    response = analyze_pagination(request)
    if not response.success:
        return JSONResponse(status_code=400, content=response.model_dump())
    return response


@router.post("/clean-data", response_model=AssistLlmResponse)
def clean_data_endpoint(request: AssistCleanDataRequest):
    response = clean_data(request)
    if not response.success:
        return JSONResponse(status_code=400, content=response.model_dump())
    return response

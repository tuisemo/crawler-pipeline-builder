from fastapi import APIRouter
from llm_client import get_default_client, get_llm_client

from .legacy_services import (
    auto_detect_page,
    clear_highlights,
    close_session,
    disable_picker,
    enable_picker,
    extract_page_html,
    generate_crawler,
    keep_session_alive,
    read_picker,
    test_fields,
    test_selector,
    visit_page,
)
from .schemas import (
    AutoDetectRequest,
    GenerateCrawlerRequest,
    PageHtmlRequest,
    SessionCloseRequest,
    TestFieldsRequest,
    TestSelectorRequest,
    VisitRequest,
)

router = APIRouter(prefix="/api", tags=["legacy"])


@router.post("/visit")
def api_visit(body: VisitRequest):
    return visit_page(body)


@router.post("/auto-detect")
def api_auto_detect(body: AutoDetectRequest):
    return auto_detect_page(body)


@router.post("/test-selector")
def api_test_selector(body: TestSelectorRequest):
    return test_selector(body)


@router.post("/test-fields")
def api_test_fields(body: TestFieldsRequest):
    return test_fields(body)


@router.post("/clear-highlights")
def api_clear_highlights(body: dict = None):
    return clear_highlights(body)


@router.post("/page-html")
def api_page_html(body: PageHtmlRequest):
    return extract_page_html(body)


@router.post("/generate-crawler")
def api_generate_crawler(body: GenerateCrawlerRequest):
    return generate_crawler(body)


@router.post("/picker-enable")
def api_picker_enable(body: dict = None):
    return enable_picker(body)


@router.post("/picker-read")
def api_picker_read(body: dict = None):
    return read_picker(body)


@router.post("/picker-disable")
def api_picker_disable(body: dict = None):
    return disable_picker(body)


@router.post("/session/close")
def api_session_close(body: SessionCloseRequest):
    return close_session(body)


@router.post("/session/keep-alive")
def api_session_keepalive(body: SessionCloseRequest):
    return keep_session_alive(body)

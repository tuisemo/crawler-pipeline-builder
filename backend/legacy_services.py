import re
import time

from fastapi.responses import JSONResponse

from extraction import AutoDetector, HtmlExtractor
from llm_client import CRAWLER_SYSTEM_PROMPT
from prompts import CrawlerPromptGenerator

from .browser_session import classify_error, get_active_session, page_session_mgr
from .js_snippets import (
    JS_CLEAR_HIGHLIGHTS,
    JS_ELEMENT_PICKER,
    JS_HIGHLIGHT_SELECTOR,
    JS_PICKER_DISABLE,
    JS_PICKER_READ,
    JS_SCAN_PAGE,
    JS_TEST_FIELDS,
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


def _error_response(error: Exception, status_code: int = 500) -> JSONResponse:
    classified = classify_error(error)
    return JSONResponse(
        {"error": classified["error"], "error_type": classified["error_type"]},
        status_code=status_code,
    )


def _scroll_for_lazy_content(page) -> None:
    last_height = 0
    for _ in range(8):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(0.5)
        height = page.evaluate("document.body.scrollHeight")
        if height == last_height:
            break
        last_height = height
    page.evaluate("window.scrollTo(0, 0)")


def _get_or_create_session(session_id: str = ""):
    session = page_session_mgr.get(session_id)
    if session is None:
        session = page_session_mgr.create()
    return session


def visit_page(body: VisitRequest):
    url = body.url.strip()
    if not url:
        return JSONResponse({"error": "URL is required"}, status_code=400)

    try:
        session = _get_or_create_session(body.session_id)
        page = session.page
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        _scroll_for_lazy_content(page)
        time.sleep(1.5)

        data = page.evaluate(JS_SCAN_PAGE)
        session.touch()
        return {"success": True, "url": url, "session_id": session.id, **data}
    except Exception as exc:
        return _error_response(exc)


def auto_detect_page(body: AutoDetectRequest):
    url = body.url.strip()
    if not url:
        return JSONResponse({"error": "URL is required"}, status_code=400)

    try:
        session = _get_or_create_session(body.session_id)
        detect_page = session.new_page()
        try:
            detect_page.goto(url, wait_until="domcontentloaded", timeout=30000)
            for _ in range(5):
                detect_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(0.5)
            detect_page.evaluate("window.scrollTo(0, 0)")
            time.sleep(1)

            result = AutoDetector().detect(detect_page)
            session.touch()
        finally:
            try:
                detect_page.close()
            except Exception:
                pass

        return {
            "success": True,
            "url": url,
            "session_id": session.id,
            "item_selector": result.item_selector,
            "item_count": result.item_count,
            "pagination_selector": result.pagination_selector,
            "pagination_strategy": result.pagination_strategy,
            "pagination_score": result.pagination_score,
            "confidence": result.confidence,
            "fields": [
                {
                    "name": field.name,
                    "selector": field.selector,
                    "type": field.extraction_type,
                    "confidence": field.confidence,
                }
                for field in result.fields
            ],
            "html_fragment": result.html_fragment,
        }
    except Exception as exc:
        return _error_response(exc)


def test_selector(body: TestSelectorRequest):
    selector = body.selector.strip()
    if not selector:
        return JSONResponse({"error": "Selector is required"}, status_code=400)

    try:
        session = _get_or_create_session(body.session_id)
        page = session.page
        page.evaluate("(" + JS_CLEAR_HIGHLIGHTS + ")()")
        result = page.evaluate("(" + JS_HIGHLIGHT_SELECTOR + ")", selector)
        session.touch()

        return {
            "success": True,
            "url": page.url,
            "session_id": session.id,
            "selector": selector,
            "extraction_type": body.extraction_type,
            "match_count": result["match_count"],
            "sample_items": result["sample_items"],
            "error": result["error"],
        }
    except Exception as exc:
        return _error_response(exc)


def test_fields(body: TestFieldsRequest):
    if not body.fields:
        return JSONResponse({"error": "At least one field is required"}, status_code=400)

    try:
        session = _get_or_create_session(body.session_id)
        page = session.page
        page.evaluate("(" + JS_CLEAR_HIGHLIGHTS + ")()")
        raw = page.evaluate(
            "(" + JS_TEST_FIELDS + ")",
            {"item_selector": body.item_selector, "fields": body.fields},
        )
        session.touch()

        return {
            "success": True,
            "url": page.url,
            "session_id": session.id,
            "field_results": raw.get("field_results", []) if isinstance(raw, dict) else [],
            "error": raw.get("error") if isinstance(raw, dict) else None,
        }
    except Exception as exc:
        return _error_response(exc)


def clear_highlights(body: dict | None = None):
    try:
        session_id = (body or {}).get("session_id", "")
        session = page_session_mgr.get(session_id)
        if session:
            session.page.evaluate(JS_CLEAR_HIGHLIGHTS)
            session.touch()
        return {"success": True}
    except Exception as exc:
        return _error_response(exc)


def extract_page_html(body: PageHtmlRequest):
    url = body.url.strip()
    item_selector = body.item_selector.strip()
    if not url:
        return JSONResponse({"error": "URL is required"}, status_code=400)

    try:
        session = _get_or_create_session(body.session_id)
        html_page = session.new_page()
        try:
            html_page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(0.5)
            selector = item_selector or "body"
            result = HtmlExtractor().extract_item_container(html_page, selector, body.max_items)
            session.touch()
        finally:
            try:
                html_page.close()
            except Exception:
                pass

        return {
            "success": True,
            "url": url,
            "session_id": session.id,
            "html": result.html,
            "truncated": result.truncated,
            "original_size": result.original_size,
            "item_count": result.item_count,
        }
    except Exception as exc:
        return _error_response(exc)


def generate_crawler(body: GenerateCrawlerRequest):
    url = body.url.strip()
    item_selector = body.item_selector.strip()
    if not url or not item_selector:
        return JSONResponse({"error": "URL and item_selector are required"}, status_code=400)

    try:
        prompt = CrawlerPromptGenerator().generate_from_simple_config(
            url=url,
            item_selector=item_selector,
            fields=body.fields,
            pagination_selector=body.pagination_selector,
            pagination_strategy=body.pagination_strategy,
            max_pages=body.max_pages,
            html_fragment=body.html_fragment,
        )

        from . import legacy_routes

        if body.llm_provider == "auto":
            client = legacy_routes.get_default_client()
            model = client.model
        else:
            model = body.llm_model or legacy_routes.get_default_client().model
            client = legacy_routes.get_llm_client(provider=body.llm_provider, model=model)

        response = client.generate_with_system(
            system=CRAWLER_SYSTEM_PROMPT,
            user=prompt,
            model=model,
        )
        if response.error:
            return JSONResponse({"error": response.error}, status_code=500)

        filename = "crawler.py"
        if "crawler_" in response.content.lower():
            match = re.search(r"crawler[_\w]*\.py", response.content, re.IGNORECASE)
            if match:
                filename = match.group(0)

        return {
            "success": True,
            "prompt": prompt,
            "script": response.content,
            "filename": filename,
            "model": response.model,
            "usage": response.usage,
        }
    except Exception as exc:
        return _error_response(exc)


def _sanitize_custom_roles(raw_custom_roles) -> list[str]:
    custom_roles: list[str] = []
    if isinstance(raw_custom_roles, list):
        for role in raw_custom_roles:
            if not isinstance(role, str):
                continue
            normalized = role.strip()
            if normalized:
                custom_roles.append(normalized[:32])
    return list(dict.fromkeys(custom_roles))


def enable_picker(body: dict | None = None):
    try:
        session_id = (body or {}).get("session_id", "")
        custom_roles = _sanitize_custom_roles((body or {}).get("custom_roles", []))
        session = page_session_mgr.get(session_id) if session_id else get_active_session()
        if session is None:
            return JSONResponse(
                {"error": "No active session. Please visit a page first."},
                status_code=400,
            )
        session.page.evaluate("(" + JS_ELEMENT_PICKER + ")", {"custom_roles": custom_roles})
        session.touch()
        return {"success": True, "session_id": session.id}
    except Exception as exc:
        return _error_response(exc)


def read_picker(body: dict | None = None):
    try:
        session_id = (body or {}).get("session_id", "")
        session = page_session_mgr.get(session_id) if session_id else get_active_session()
        if session is None:
            return JSONResponse({"error": "No active session"}, status_code=400)
        result = session.page.evaluate("(" + JS_PICKER_READ + ")()")
        session.touch()
        return {"success": True, "element": result}
    except Exception as exc:
        return _error_response(exc)


def disable_picker(body: dict | None = None):
    try:
        session_id = (body or {}).get("session_id", "")
        session = page_session_mgr.get(session_id) if session_id else get_active_session()
        if session:
            session.page.evaluate("(" + JS_PICKER_DISABLE + ")()")
            session.touch()
        return {"success": True}
    except Exception as exc:
        return _error_response(exc)


def close_session(body: SessionCloseRequest):
    closed = page_session_mgr.close(body.session_id)
    return {"success": closed, "session_id": body.session_id}


def keep_session_alive(body: SessionCloseRequest):
    session = page_session_mgr.get(body.session_id)
    if session:
        session.touch()
        return {"success": True, "session_id": body.session_id}
    return JSONResponse({"error": "Session not found"}, status_code=404)

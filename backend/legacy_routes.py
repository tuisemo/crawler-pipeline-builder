import time
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from .schemas import (
    VisitRequest, AutoDetectRequest, TestSelectorRequest, 
    TestFieldsRequest, PageHtmlRequest, GenerateCrawlerRequest,
    SessionCloseRequest
)
from .browser_session import page_session_mgr, get_active_session, classify_error
from .js_snippets import (
    JS_SCAN_PAGE, JS_ELEMENT_PICKER, JS_PICKER_READ, JS_PICKER_DISABLE,
    JS_CLEAR_HIGHLIGHTS, JS_HIGHLIGHT_SELECTOR, JS_TEST_FIELDS
)
from extraction import AutoDetector, SelectorTester, HtmlExtractor
from prompts import CrawlerPromptGenerator
from llm_client import get_llm_client, get_default_client, CRAWLER_SYSTEM_PROMPT

router = APIRouter(prefix="/api", tags=["legacy"])

@router.post("/visit")
def api_visit(body: VisitRequest):
    url = body.url.strip()
    if not url:
        return JSONResponse({"error": "URL is required"}, status_code=400)

    try:
        session = page_session_mgr.get(body.session_id)
        if session is None:
            session = page_session_mgr.create()

        page = session.page
        page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # Scroll to trigger lazy loading
        def scroll_load():
            last = 0
            for _ in range(8):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(0.5)
                h = page.evaluate("document.body.scrollHeight")
                if h == last:
                    break
                last = h
            page.evaluate("window.scrollTo(0, 0)")

        scroll_load()
        time.sleep(1.5)

        data = page.evaluate(JS_SCAN_PAGE)
        session.touch()

        return {"success": True, "url": url, "session_id": session.id, **data}
    except Exception as e:
        err = classify_error(e); return JSONResponse({"error": err["error"], "error_type": err["error_type"]}, status_code=500)


@router.post("/auto-detect")
def api_auto_detect(body: AutoDetectRequest):
    url = body.url.strip()
    if not url:
        return JSONResponse({"error": "URL is required"}, status_code=400)

    try:
        session = page_session_mgr.get(body.session_id)
        if session is None:
            session = page_session_mgr.create()

        detect_page = session.new_page()
        try:
            detect_page.goto(url, wait_until="domcontentloaded", timeout=30000)

            for _ in range(5):
                detect_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(0.5)
            detect_page.evaluate("window.scrollTo(0, 0)")
            time.sleep(1)

            detector = AutoDetector()
            result = detector.detect(detect_page)
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
                    "name": f.name,
                    "selector": f.selector,
                    "type": f.extraction_type,
                    "confidence": f.confidence
                }
                for f in result.fields
            ],
            "html_fragment": result.html_fragment
        }
    except Exception as e:
        err = classify_error(e); return JSONResponse({"error": err["error"], "error_type": err["error_type"]}, status_code=500)

@router.post("/test-selector")
def api_test_selector(body: TestSelectorRequest):
    url = body.url.strip()
    selector = body.selector.strip()
    extraction_type = body.extraction_type

    if not selector:
        return JSONResponse({"error": "Selector is required"}, status_code=400)

    try:
        session = page_session_mgr.get(body.session_id)
        if session is None:
            session = page_session_mgr.create()

        page = session.page

        page.evaluate("(" + JS_CLEAR_HIGHLIGHTS + ")()")
        result = page.evaluate("(" + JS_HIGHLIGHT_SELECTOR + ")", selector)
        session.touch()

        return {
            "success": True,
            "url": page.url,
            "session_id": session.id,
            "selector": selector,
            "extraction_type": extraction_type,
            "match_count": result["match_count"],
            "sample_items": result["sample_items"],
            "error": result["error"]
        }
    except Exception as e:
        err = classify_error(e); return JSONResponse({"error": err["error"], "error_type": err["error_type"]}, status_code=500)

@router.post("/test-fields")
def api_test_fields(body: TestFieldsRequest):
    if not body.fields:
        return JSONResponse({"error": "At least one field is required"}, status_code=400)

    try:
        session = page_session_mgr.get(body.session_id)
        if session is None:
            session = page_session_mgr.create()

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
            "error": raw.get("error") if isinstance(raw, dict) else None
        }
    except Exception as e:
        err = classify_error(e); return JSONResponse({"error": err["error"], "error_type": err["error_type"]}, status_code=500)


@router.post("/clear-highlights")
def api_clear_highlights(body: dict = None):
    try:
        session_id = (body or {}).get("session_id", "")
        session = page_session_mgr.get(session_id)
        if session:
            session.page.evaluate(JS_CLEAR_HIGHLIGHTS)
            session.touch()
        return {"success": True}
    except Exception as e:
        err = classify_error(e); return JSONResponse({"error": err["error"], "error_type": err["error_type"]}, status_code=500)


@router.post("/page-html")
def api_page_html(body: PageHtmlRequest):
    url = body.url.strip()
    item_selector = body.item_selector.strip()

    if not url:
        return JSONResponse({"error": "URL is required"}, status_code=400)

    try:
        session = page_session_mgr.get(body.session_id)
        if session is None:
            session = page_session_mgr.create()

        html_page = session.new_page()
        try:
            html_page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(0.5)

            extractor = HtmlExtractor()

            if item_selector:
                result = extractor.extract_item_container(html_page, item_selector, body.max_items)
            else:
                result = extractor.extract_item_container(html_page, "body", body.max_items)
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
            "item_count": result.item_count
        }
    except Exception as e:
        err = classify_error(e); return JSONResponse({"error": err["error"], "error_type": err["error_type"]}, status_code=500)

@router.post("/generate-crawler")
def api_generate_crawler(body: GenerateCrawlerRequest):
    url = body.url.strip()
    item_selector = body.item_selector.strip()

    if not url or not item_selector:
        return JSONResponse({"error": "URL and item_selector are required"}, status_code=400)

    try:
        generator = CrawlerPromptGenerator()
        prompt = generator.generate_from_simple_config(
            url=url,
            item_selector=item_selector,
            fields=body.fields,
            pagination_selector=body.pagination_selector,
            pagination_strategy=body.pagination_strategy,
            max_pages=body.max_pages,
            html_fragment=body.html_fragment
        )

        if body.llm_provider == "auto":
            client = get_default_client()
            model = client.model
        else:
            if body.llm_model:
                model = body.llm_model
            else:
                default_client = get_default_client()
                model = default_client.model
            client = get_llm_client(provider=body.llm_provider, model=model)

        response = client.generate_with_system(
            system=CRAWLER_SYSTEM_PROMPT,
            user=prompt,
            model=model
        )

        if response.error:
            return JSONResponse({"error": response.error}, status_code=500)

        filename = "crawler.py"
        if "crawler_" in response.content.lower():
            import re
            match = re.search(r'crawler[_\w]*\.py', response.content, re.IGNORECASE)
            if match:
                filename = match.group(0)

        return {
            "success": True,
            "prompt": prompt,
            "script": response.content,
            "filename": filename,
            "model": response.model,
            "usage": response.usage
        }
    except Exception as e:
        err = classify_error(e); return JSONResponse({"error": err["error"], "error_type": err["error_type"]}, status_code=500)

@router.post("/picker-enable")
def api_picker_enable(body: dict = None):
    try:
        session_id = (body or {}).get("session_id", "")
        raw_custom_roles = (body or {}).get("custom_roles", [])
        custom_roles: list[str] = []
        if isinstance(raw_custom_roles, list):
            for role in raw_custom_roles:
                if not isinstance(role, str):
                    continue
                normalized = role.strip()
                if not normalized:
                    continue
                custom_roles.append(normalized[:32])
        custom_roles = list(dict.fromkeys(custom_roles))

        session = page_session_mgr.get(session_id) if session_id else get_active_session()
        if session is None:
            return JSONResponse({"error": "No active session. Please visit a page first."}, status_code=400)
        session.page.evaluate("(" + JS_ELEMENT_PICKER + ")", {"custom_roles": custom_roles})
        session.touch()
        return {"success": True, "session_id": session.id}
    except Exception as e:
        err = classify_error(e); return JSONResponse({"error": err["error"], "error_type": err["error_type"]}, status_code=500)

@router.post("/picker-read")
def api_picker_read(body: dict = None):
    try:
        session_id = (body or {}).get("session_id", "")
        session = page_session_mgr.get(session_id) if session_id else get_active_session()
        if session is None:
            return JSONResponse({"error": "No active session"}, status_code=400)
        result = session.page.evaluate("(" + JS_PICKER_READ + ")()")
        session.touch()
        return {"success": True, "element": result}
    except Exception as e:
        err = classify_error(e); return JSONResponse({"error": err["error"], "error_type": err["error_type"]}, status_code=500)

@router.post("/picker-disable")
def api_picker_disable(body: dict = None):
    try:
        session_id = (body or {}).get("session_id", "")
        session = page_session_mgr.get(session_id) if session_id else get_active_session()
        if session:
            session.page.evaluate("(" + JS_PICKER_DISABLE + ")()")
            session.touch()
        return {"success": True}
    except Exception as e:
        err = classify_error(e); return JSONResponse({"error": err["error"], "error_type": err["error_type"]}, status_code=500)


@router.post("/session/close")
def api_session_close(body: SessionCloseRequest):
    closed = page_session_mgr.close(body.session_id)
    return {"success": closed, "session_id": body.session_id}

@router.post("/session/keep-alive")
def api_session_keepalive(body: SessionCloseRequest):
    session = page_session_mgr.get(body.session_id)
    if session:
        session.touch()
        return {"success": True, "session_id": body.session_id}
    return JSONResponse({"error": "Session not found"}, status_code=404)

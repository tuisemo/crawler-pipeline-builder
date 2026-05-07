"""Assist services for AI-guided workflow authoring."""

from __future__ import annotations

import json
import logging
import re
from html import unescape
from typing import Any

from backend.core.app_logging import audit_event
from backend.extraction.auto_detector import AutoDetector
from backend.extraction.html_extractor import HtmlExtractor
from backend.extraction.selector_tester import SelectorTester
from backend.llm import (
    get_default_client,
)
from backend.prompts.assemblers.assist import (
    build_field_inference_prompt,
    build_selector_optimization_prompt,
)
from backend.prompts.contracts.assist_contracts import (
    FIELD_INFERENCE_RESPONSE_CONTRACT,
    PAGINATION_ANALYSIS_RESPONSE_CONTRACT,
    SELECTOR_OPTIMIZATION_RESPONSE_CONTRACT,
)

logger = logging.getLogger(__name__)

from backend.assist.json_protocol import (
    JSON_REPAIR_SYSTEM_PROMPT,
    _build_json_repair_prompt,
    _build_json_task_system_prompt,
    _extract_json_payload,
)
from backend.assist.pagination_recovery import (
    _NEXT_TEXT_RE,
    PAGINATION_ANALYSIS_SYSTEM_RULES,
    build_pagination_analysis_user_prompt,
    has_pagination_evidence,
    is_semantically_empty_pagination_result,
    recover_pagination_from_summary,
    recover_partial_pagination_json,
)
from backend.runtime.browser_session import get_active_session, page_session_mgr
from backend.runtime.ext_session_mgr import ext_session_mgr
from backend.workflow.schemas import (
    AssistLlmRequest,
    AssistLlmResponse,
    AssistHtmlExtractRequest,
    AssistHtmlExtractResponse,
    AssistSelectorTestRequest,
    AssistSelectorTestResponse,
    AutoDetectRequest,
    AutoDetectResponse,
)

PLAYWRIGHT_ONLY_SELECTOR_MARKERS = (
    "locator(",
    "get_by_role(",
    "get_by_text(",
    "text=",
    "nth=",
    ">>",
    ":has-text(",
)


def _is_extension_session(session: Any) -> bool:
    return hasattr(session, "clear_highlight") and (
        hasattr(session, "auto_detect")
        or hasattr(session, "extract_html")
        or hasattr(session, "test_selector")
    )


def _confidence_bucket(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "unknown"
    if value >= 0.85:
        return "high"
    if value >= 0.6:
        return "medium"
    return "low"


def _emit_assist_prompt_quality_metric(
    *,
    task_name: str,
    success: bool,
    user_prompt: str,
    raw_output: str,
    model: str | None,
    usage: dict[str, Any] | None,
    confidence: object,
    error_code: str | None,
    json_valid_first_pass: bool,
    used_partial_recovery: bool,
    used_repair_pass: bool,
    used_semantic_retry: bool,
    used_heuristic_fallback: bool,
    semantic_empty_detected: bool,
) -> None:
    audit_event(
        "assist_prompt_quality_metric",
        task_name=task_name,
        success=success,
        error_code=error_code,
        model=model or "",
        prompt_chars=len(user_prompt or ""),
        output_chars=len(raw_output or ""),
        usage=usage or {},
        confidence_bucket=_confidence_bucket(confidence),
        json_valid_first_pass=json_valid_first_pass,
        used_partial_recovery=used_partial_recovery,
        used_repair_pass=used_repair_pass,
        used_semantic_retry=used_semantic_retry,
        used_heuristic_fallback=used_heuristic_fallback,
        semantic_empty_detected=semantic_empty_detected,
    )


def _extract_html_section(section_name: str, html_fragment: str) -> str:
    pattern = re.compile(
        rf"<!--\s*{re.escape(section_name)}\s*-->\s*([\s\S]*?)(?:<!--\s*[A-Z_]+\s*-->|$)",
        re.IGNORECASE,
    )
    match = pattern.search(html_fragment or "")
    return match.group(1).strip() if match else ""


def _normalize_runtime_selector(selector: str) -> str:
    normalized = (selector or "").strip()
    if not normalized:
        return ""
    lowered = normalized.lower()
    if lowered.startswith(("xpath=", "css=")):
        return normalized
    if normalized.startswith(("//", ".//", "(//", "(/")):
        return f"xpath={normalized}"
    return normalized


def _is_query_compatible_selector(selector: str) -> bool:
    lowered = selector.lower()
    return not any(marker in lowered for marker in PLAYWRIGHT_ONLY_SELECTOR_MARKERS)


def _get_live_session_for_selector_validation(session_id: str | None):
    session = page_session_mgr.get(session_id) if session_id else get_active_session()
    if session is not None and session.is_alive():
        return session
    return None


def _selector_matches_session_page(session, selector: str) -> tuple[bool, str]:
    normalized = _normalize_runtime_selector(selector)
    if not normalized:
        return False, normalized
    if not _is_query_compatible_selector(normalized):
        return False, normalized
    try:
        return len(session.page.query_selector_all(normalized)) > 0, normalized
    except Exception:
        return False, normalized


def _element_looks_like_next_control(element: Any) -> bool | None:
    inspected = False
    try:
        rel = str(element.get_attribute("rel") or "").strip().lower()
        inspected = True
        if rel == "next":
            return True
    except Exception:
        pass

    for attr_name in ("aria-label", "title", "class"):
        try:
            attr_value = str(element.get_attribute(attr_name) or "").strip()
            inspected = True
        except Exception:
            attr_value = ""
        if not attr_value:
            continue
        if _NEXT_TEXT_RE.search(attr_value):
            return True
        if attr_name == "class" and re.search(r"(?:^|\b)(next|more|load-more|load_more)(?:\b|$)", attr_value, re.IGNORECASE):
            return True

    try:
        text = re.sub(r"\s+", " ", str(element.inner_text() or "")).strip()
        inspected = True
    except Exception:
        text = ""
    if text and _NEXT_TEXT_RE.search(text):
        return True
    if inspected:
        return False
    return None


def _validate_actionable_pagination_selector(session: Any, strategy: str, selector: str) -> tuple[bool, str, str | None]:
    normalized = _normalize_runtime_selector(selector)
    if not normalized:
        return False, normalized, "Selector is empty after normalization."
    if not _is_query_compatible_selector(normalized):
        return False, normalized, "Selector is not compatible with direct DOM or Playwright query execution."

    try:
        matches = session.page.query_selector_all(normalized)
    except Exception:
        return False, normalized, "Selector execution failed against the current page session."

    match_count = len(matches)
    if match_count == 0:
        return False, normalized, "Selector did not match any pagination control on the current page session."

    normalized_strategy = (strategy or "").strip().lower()
    if normalized_strategy in {"click_next", "load_more"}:
        if match_count > 1:
            return False, normalized, f"Selector matched {match_count} elements; next/load-more control selectors must resolve to a single actionable element."
        next_signal = _element_looks_like_next_control(matches[0])
        if next_signal is False:
            return False, normalized, "Selector matched one element, but it does not look like a concrete next/load-more control."

    return True, normalized, None


def _extract_item_samples(html_fragment: str) -> list[str]:
    item_samples = _extract_html_section("ITEM_SAMPLES", html_fragment) or html_fragment or ""
    return [line.strip() for line in item_samples.splitlines() if line.strip().startswith("<")]


def _extract_shared_item_selector_from_samples(samples: list[str]) -> str:
    if not samples:
        return ""
    opening_tags = [re.match(r"<([a-zA-Z0-9]+)([^>]*)>", sample) for sample in samples]
    opening_tags = [match for match in opening_tags if match]
    if not opening_tags:
        return ""
    tag = opening_tags[0].group(1).lower()
    class_sets: list[list[str]] = []
    for match in opening_tags:
        attrs = match.group(2)
        class_match = re.search(r'class="([^"]+)"', attrs)
        if not class_match:
            class_sets.append([])
            continue
        class_sets.append(_stable_class_tokens(class_match.group(1)))
    shared = class_sets[0]
    for token_list in class_sets[1:]:
        token_set = set(token_list)
        shared = [token for token in shared if token in token_set]
        if not shared:
            break
    if shared:
        return f'{tag}.{".".join(shared)}'
    return tag


def _selector_from_tag_and_class(tag: str, class_name: str) -> str:
    classes = _stable_class_tokens(class_name)
    if classes:
        return f'{tag}.{".".join(classes)}'
    return tag


def _extract_text_candidates(sample_html: str, pattern: str) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for match in re.finditer(pattern, sample_html, re.IGNORECASE | re.DOTALL):
        tag = match.group("tag").lower()
        attrs = match.group("attrs") or ""
        text = re.sub(r"<[^>]+>", " ", match.group("text") or "")
        text = re.sub(r"\s+", " ", unescape(text)).strip()
        class_match = re.search(r'class="([^"]+)"', attrs)
        candidates.append({
            "tag": tag,
            "class": class_match.group(1) if class_match else "",
            "text": text,
        })
    return candidates


def _heuristic_infer_fields(html_fragment: str) -> dict[str, Any] | None:
    samples = _extract_item_samples(html_fragment)
    if not samples:
        return None

    first = samples[0]
    fields: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def add_field(name: str, selector: str, field_type: str, confidence: float):
        key = (name, selector, field_type)
        if not selector or key in seen:
            return
        seen.add(key)
        fields.append({
            "name": name,
            "selector": selector,
            "type": field_type,
            "confidence": confidence,
        })

    title_candidates = _extract_text_candidates(
        first,
        r"<(?P<tag>h[1-6]|a|p|span|div)(?P<attrs>[^>]*)>(?P<text>.*?)</(?P=tag)>",
    )
    for candidate in title_candidates:
        text = candidate["text"]
        class_name = candidate["class"]
        if not text or len(text) < 6 or len(text) > 220:
            continue
        if candidate["tag"].startswith("h") or re.search(r"(title|tit|name|heading)", class_name, re.IGNORECASE):
            add_field("title", _selector_from_tag_and_class(candidate["tag"], class_name), "text", 0.9)
            break
    if not any(field["name"] == "title" for field in fields):
        for candidate in title_candidates:
            text = candidate["text"]
            if candidate["tag"] == "a" and 6 <= len(text) <= 220:
                add_field("title", _selector_from_tag_and_class(candidate["tag"], candidate["class"]), "text", 0.78)
                break

    image_match = re.search(r"<img(?P<attrs>[^>]*)>", first, re.IGNORECASE)
    if image_match:
        attrs = image_match.group("attrs") or ""
        class_match = re.search(r'class="([^"]+)"', attrs)
        add_field("image", _selector_from_tag_and_class("img", class_match.group(1) if class_match else ""), "attr:src", 0.86)

    link_match = re.search(r"<a(?P<attrs>[^>]*)href=\"[^\"]+\"[^>]*>(?P<text>.*?)</a>", first, re.IGNORECASE | re.DOTALL)
    if link_match:
        attrs = link_match.group("attrs") or ""
        class_match = re.search(r'class="([^"]+)"', attrs)
        link_text = re.sub(r"<[^>]+>", " ", link_match.group("text") or "")
        link_text = re.sub(r"\s+", " ", unescape(link_text)).strip()
        confidence = 0.82 if len(link_text) >= 6 else 0.68
        add_field("link", _selector_from_tag_and_class("a", class_match.group(1) if class_match else ""), "attr:href", confidence)

    date_candidates = _extract_text_candidates(
        first,
        r"<(?P<tag>span|em|time|p|div)(?P<attrs>[^>]*)>(?P<text>.*?)</(?P=tag)>",
    )
    for candidate in date_candidates:
        text = candidate["text"]
        class_name = candidate["class"]
        if re.search(r"(date|time|sj)", class_name, re.IGNORECASE) or re.search(r"\d{4}[-./年]\d{1,2}[-./月]?\d{0,2}", text):
            add_field("date", _selector_from_tag_and_class(candidate["tag"], class_name), "text", 0.8)
            break

    for candidate in title_candidates:
        text = candidate["text"]
        if candidate["tag"] == "p" and len(text) >= 40:
            add_field("summary", _selector_from_tag_and_class(candidate["tag"], candidate["class"]), "text", 0.72)
            break

    if not fields:
        return None

    return {
        "item_selector": _extract_shared_item_selector_from_samples(samples),
        "fields": fields[:6],
        "confidence": 0.62,
        "reason": "Recovered from deterministic HTML heuristics because the model returned an empty field inference result.",
    }


def _heuristic_optimize_selector(initial_selector: str, html_fragment: str) -> dict[str, Any] | None:
    selector = (initial_selector or "").strip()
    if not selector:
        return None

    optimized = selector
    reason_parts: list[str] = []

    optimized = re.sub(r"\.(?:clearfix|clear|active|current|selected)\b", "", optimized)
    optimized = re.sub(r"\.item-\d+\b", "", optimized)
    optimized = re.sub(r"\.w-node-[a-zA-Z0-9_-]+\b", "", optimized)
    optimized = re.sub(r"\s{2,}", " ", optimized).strip()

    if optimized != selector:
        reason_parts.append("Removed utility or volatile classes that are unlikely to be semantic.")

    if "#" in optimized:
        repeated_id_match = re.search(r'id="([^"]+)"', html_fragment)
        if repeated_id_match and html_fragment.count(f'id="{repeated_id_match.group(1)}"') > 1:
            shared_selector = _extract_shared_item_selector_from_samples(_extract_item_samples(html_fragment))
            if shared_selector:
                optimized = shared_selector
                reason_parts.append("Replaced a duplicated ID-based selector with a shared tag/class selector derived from repeated item samples.")

    optimized = re.sub(r"\s+\>\s+", " > ", optimized).strip()
    optimized = re.sub(r"\.{2,}", ".", optimized)

    if not optimized:
        return None

    if not reason_parts:
        reason_parts.append("The current selector is already stable enough based on the repeated item structure in the provided HTML.")

    return {
        "optimized_selector": optimized,
        "confidence": 0.78 if optimized != selector else 0.92,
        "reason": " ".join(reason_parts),
    }


def _normalize_assist_json_result(task_name: str, parsed: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(parsed)

    if task_name == "infer_fields":
        normalized["item_selector"] = normalized.get("item_selector") if isinstance(normalized.get("item_selector"), str) else ""
        fields = normalized.get("fields")
        normalized["fields"] = fields if isinstance(fields, list) else []
    elif task_name == "optimize_selector":
        normalized["optimized_selector"] = normalized.get("optimized_selector") if isinstance(normalized.get("optimized_selector"), str) else ""
    elif task_name == "analyze_pagination":
        strategy = normalized.get("pagination_strategy")
        normalized["pagination_strategy"] = strategy if isinstance(strategy, str) else "none"
        normalized["next_button_selector"] = normalized.get("next_button_selector") if isinstance(normalized.get("next_button_selector"), str) else ""
        page_selectors = normalized.get("page_number_selectors")
        normalized["page_number_selectors"] = page_selectors if isinstance(page_selectors, list) else []
        normalized["item_selector"] = normalized.get("item_selector") if isinstance(normalized.get("item_selector"), str) else ""
    confidence = normalized.get("confidence")
    if not isinstance(confidence, (int, float)):
        normalized["confidence"] = None

    reason = normalized.get("reason")
    if not isinstance(reason, str):
        normalized["reason"] = None

    return normalized


def _stable_class_tokens(class_name: str) -> list[str]:
    tokens = []
    for token in re.split(r"\s+", class_name.strip()):
        cleaned = token.strip()
        if not cleaned or any(ch.isdigit() for ch in cleaned) or len(cleaned) > 40:
            continue
        if re.match(r"^[a-zA-Z_-][a-zA-Z0-9_-]*$", cleaned):
            tokens.append(cleaned)
    return tokens[:2]


def _attempt_semantic_retry(
    client: Any,
    user_prompt: str,
    task_name: str,
    response_contract: str,
    previous_output: str,
    system_suffix: str = "",
) -> tuple[dict[str, Any] | None, Any]:
    retry_response = client.generate_with_system(
        system=(
            f"{_build_json_task_system_prompt(response_contract, system_suffix=system_suffix)}\n\n"
            "The previous answer was semantically empty. If pagination evidence exists, do not return an all-empty `none` result."
        ),
        user=(
            f"{user_prompt}\n\n"
            "Previous model output was semantically empty and should be treated as invalid for this task:\n"
            f"{previous_output}"
        ),
        temperature=0.05,
        max_tokens=4000,
        response_format={"type": "json_object"},
        request_name=f"assist_{task_name}_semantic_retry",
    )
    if retry_response.error:
        return None, retry_response
    parsed = _extract_json_payload(retry_response.content or "")
    if parsed is None:
        return None, retry_response
    normalized = _normalize_assist_json_result(task_name, parsed)
    return normalized, retry_response


def _attempt_repair_json_payload(client: Any, raw_output: str, response_contract: str) -> tuple[dict[str, Any] | None, Any]:
    repair_response = client.generate_with_system(
        system=f"{JSON_REPAIR_SYSTEM_PROMPT}\n\n{response_contract}",
        user=_build_json_repair_prompt(response_contract, raw_output),
        temperature=0,
        max_tokens=1200,
        response_format={"type": "json_object"},
        request_name="assist_json_repair",
    )
    if repair_response.error:
        return None, repair_response
    return _extract_json_payload(repair_response.content or ""), repair_response


def _ensure_session(session_id: str | None, url: str | None, agent_id: str | None = None):
    extension_agent_id = agent_id[4:] if agent_id and agent_id.startswith("ext:") else None
    session = None
    navigated_during_create = False

    if session_id:
        if extension_agent_id:
            session = ext_session_mgr.get(session_id)
        else:
            session = page_session_mgr.get(session_id)
        if session is not None and session.is_alive():
            pass
        else:
            if session and extension_agent_id:
                ext_session_mgr.close(session_id)
            elif session:
                page_session_mgr.close(session_id)
            session = None

    if session is None:
        if extension_agent_id:
            try:
                session = ext_session_mgr.create(extension_agent_id, url)
                navigated_during_create = bool(url)
            except RuntimeError as e:
                return None, str(e)
        elif url and not session_id:
            session = page_session_mgr.create()
        else:
            session = get_active_session()
            if session is not None and not session.is_alive():
                page_session_mgr.close(session.id)
                session = None

            if session is None:
                session = page_session_mgr.create()

    if url:
        try:
            if not navigated_during_create:
                session.navigate(url, timeout=30000)
        except Exception as e:
            return None, f"Failed to navigate: {str(e)}"
            
    return session, None


def auto_detect(request: AutoDetectRequest) -> AutoDetectResponse:
    audit_event(
        "assist_auto_detect_started",
        session_id=request.session_id,
        url=request.url,
    )
    session, error = _ensure_session(request.session_id, request.url, getattr(request, "agent_id", None))
    if error:
        audit_event(
            "assist_auto_detect_failed",
            session_id=request.session_id,
            url=request.url,
            error=error,
        )
        return AutoDetectResponse(success=False, error=error)

    if _is_extension_session(session):
        session.clear_highlight()
        raw = session.auto_detect()
        audit_event(
            "assist_auto_detect_completed",
            session_id=session.id,
            url=request.url,
            result=raw,
        )
        return AutoDetectResponse(
            success=True,
            session_id=session.id,
            result={
                "item_selector": raw.get("item_selector", ""),
                "item_count": raw.get("item_count", 0),
                "item_signature": raw.get("item_signature", ""),
                "pagination_selector": raw.get("pagination_selector", ""),
                "pagination_strategy": raw.get("pagination_strategy", "none"),
                "pagination_score": raw.get("pagination_score", 0),
                "confidence": raw.get("confidence", 0.0),
                "fields": raw.get("fields", []),
                "html_fragment": raw.get("html_fragment", ""),
            },
        )

    SelectorTester.clear_selector_highlight(session.page)
    detector = AutoDetector()
    result = detector.detect(session.page)
    audit_event(
        "assist_auto_detect_completed",
        session_id=session.id,
        url=request.url,
        result={
            "item_selector": result.item_selector,
            "item_count": result.item_count,
            "item_signature": result.item_signature,
            "pagination_selector": result.pagination_selector,
            "pagination_strategy": result.pagination_strategy,
            "pagination_score": result.pagination_score,
            "confidence": result.confidence,
            "field_count": len(result.fields),
            "html_fragment": result.html_fragment,
        },
    )
    return AutoDetectResponse(
        success=True,
        session_id=session.id,
        result={
            "item_selector": result.item_selector,
            "item_count": result.item_count,
            "item_signature": result.item_signature,
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
        },
    )


def run_selector_test(request: AssistSelectorTestRequest) -> AssistSelectorTestResponse:
    session, error = _ensure_session(request.session_id, request.url, getattr(request, "agent_id", None))
    if error:
        audit_event(
            "assist_test_selector_failed",
            session_id=request.session_id,
            url=request.url,
            selector=request.selector,
            error=error,
        )
        return AssistSelectorTestResponse(success=False, error=error)

    if _is_extension_session(session):
        session.clear_highlight()
        ext_result = session.test_selector(
            request.selector,
            max_samples=request.max_samples if isinstance(request.max_samples, int) and request.max_samples > 0 else 5,
        )
        if ext_result.get("error"):
            error = str(ext_result.get("error"))
            audit_event(
                "assist_test_selector_failed",
                session_id=session.id,
                url=request.url,
                selector=request.selector,
                error=error,
            )
            return AssistSelectorTestResponse(success=False, session_id=session.id, error=error)
        highlighted_count = 0
        if int(ext_result.get("count", 0)) > 0:
            highlighted_count = session.highlight_selector(
                request.selector,
                clear_after_ms=request.clear_after_ms,
            )
        payload = {
            "match_count": int(ext_result.get("count", 0)),
            "highlighted_count": highlighted_count,
            "clear_after_ms": request.clear_after_ms,
            "sample_items": ext_result.get("elements", []),
        }
    else:
        SelectorTester.clear_selector_highlight(session.page)
        result = SelectorTester.test_selector(
            session.page,
            request.selector,
            max_samples=request.max_samples if isinstance(request.max_samples, int) and request.max_samples > 0 else 5,
        )
        if result.error:
            audit_event(
                "assist_test_selector_failed",
                session_id=session.id,
                url=request.url,
                selector=request.selector,
                error=result.error,
            )
            return AssistSelectorTestResponse(success=False, session_id=session.id, error=result.error)

        highlighted_count = 0
        if result.match_count > 0:
            highlighted_count = SelectorTester.highlight_selector(
                session.page,
                request.selector,
                clear_after_ms=request.clear_after_ms,
            )

        payload = {
            "match_count": result.match_count,
            "highlighted_count": highlighted_count,
            "clear_after_ms": request.clear_after_ms,
            "sample_items": result.sample_items,
        }
    audit_event(
        "assist_test_selector_completed",
        session_id=session.id,
        url=request.url,
        selector=request.selector,
        result=payload,
    )
    return AssistSelectorTestResponse(
        success=True,
        session_id=session.id,
        result=payload,
    )


def extract_html_fragment(request: AssistHtmlExtractRequest) -> AssistHtmlExtractResponse:
    session, error = _ensure_session(request.session_id, request.url, getattr(request, "agent_id", None))
    if error:
        audit_event(
            "assist_extract_html_failed",
            session_id=request.session_id,
            url=request.url,
            item_selector=request.item_selector,
            include_pagination=request.include_pagination,
            max_items=request.max_items,
            error=error,
        )
        return AssistHtmlExtractResponse(success=False, error=error)

    if _is_extension_session(session):
        session.clear_highlight()
        ext_result = session.extract_html(
            request.item_selector,
            max_items=request.max_items,
            include_pagination=request.include_pagination,
        )
        html_fragment = str(ext_result.get("html", ""))
        metadata = {
            "truncated": bool(ext_result.get("truncated", False)),
            "original_size": int(ext_result.get("original_size", len(html_fragment.encode("utf-8")))),
            "truncated_size": int(ext_result.get("truncated_size", len(html_fragment.encode("utf-8")))),
            "item_count": int(ext_result.get("item_count", 0)),
        }
        audit_event(
            "assist_extract_html_completed",
            session_id=session.id,
            url=request.url,
            item_selector=request.item_selector,
            include_pagination=request.include_pagination,
            max_items=request.max_items,
            html_fragment=html_fragment,
            metadata=metadata,
        )
        return AssistHtmlExtractResponse(
            success=True,
            session_id=session.id,
            html_fragment=html_fragment,
            metadata=metadata,
        )

    SelectorTester.clear_selector_highlight(session.page)
    extractor = HtmlExtractor()
    if request.include_pagination:
        result = extractor.extract_pagination_context(
            session.page,
            request.item_selector,
            max_items=request.max_items,
        )
    else:
        result = extractor.extract_item_container(
            session.page,
            request.item_selector,
            max_items=request.max_items,
        )
    audit_event(
        "assist_extract_html_completed",
        session_id=session.id,
        url=request.url,
        item_selector=request.item_selector,
        include_pagination=request.include_pagination,
        max_items=request.max_items,
        html_fragment=result.html,
        metadata={
            "truncated": result.truncated,
            "original_size": result.original_size,
            "truncated_size": result.truncated_size,
            "item_count": result.item_count,
            "has_item_samples": "<!-- ITEM_SAMPLES -->" in result.html,
            "has_pagination_html": "<!-- PAGINATION -->" in result.html,
            "has_pagination_summary": "<!-- PAGINATION_CONTROL_SUMMARY -->" in result.html,
        },
    )
    return AssistHtmlExtractResponse(
        success=True,
        session_id=session.id,
        html_fragment=result.html,
        metadata={
            "truncated": result.truncated,
            "original_size": result.original_size,
            "truncated_size": result.truncated_size,
            "item_count": result.item_count,
        },
    )


def _run_llm_json_task(
    user_prompt: str,
    task_name: str,
    response_contract: str,
    system_suffix: str = "",
    max_tokens: int = 1500,
) -> AssistLlmResponse:
    quality = {
        "json_valid_first_pass": False,
        "used_partial_recovery": False,
        "used_repair_pass": False,
        "used_semantic_retry": False,
        "used_heuristic_fallback": False,
        "semantic_empty_detected": False,
    }

    def _return_with_quality(result: AssistLlmResponse, error_code: str | None = None) -> AssistLlmResponse:
        confidence = None
        if isinstance(result.result, dict):
            confidence = result.result.get("confidence")
        elif isinstance(result.confidence, (int, float)):
            confidence = result.confidence

        _emit_assist_prompt_quality_metric(
            task_name=task_name,
            success=result.success,
            user_prompt=user_prompt,
            raw_output=result.raw or "",
            model=result.model,
            usage=result.usage if isinstance(result.usage, dict) else None,
            confidence=confidence,
            error_code=error_code,
            json_valid_first_pass=quality["json_valid_first_pass"],
            used_partial_recovery=quality["used_partial_recovery"],
            used_repair_pass=quality["used_repair_pass"],
            used_semantic_retry=quality["used_semantic_retry"],
            used_heuristic_fallback=quality["used_heuristic_fallback"],
            semantic_empty_detected=quality["semantic_empty_detected"],
        )
        return result

    audit_event(
        "assist_task_started",
        task_name=task_name,
        response_contract=response_contract,
        user_prompt=user_prompt,
    )
    try:
        client = get_default_client()
        response = client.generate_with_system(
            system=_build_json_task_system_prompt(response_contract, system_suffix=system_suffix),
            user=user_prompt,
            temperature=0.1,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            request_name=f"assist_{task_name}",
        )
    except Exception as error:
        logger.exception("Assist task failed before LLM response", extra={"task_name": task_name})
        audit_event("assist_task_exception", task_name=task_name, error=str(error))
        return _return_with_quality(
            AssistLlmResponse(success=False, error=str(error), raw=""),
            error_code="assist_task_exception",
        )

    if response.error:
        audit_event("assist_task_llm_error", task_name=task_name, error=response.error)
        return _return_with_quality(
            AssistLlmResponse(success=False, error=response.error, raw=response.content, model=response.model, usage=response.usage),
            error_code="assist_task_llm_error",
        )

    parsed = _extract_json_payload(response.content or "")
    quality["json_valid_first_pass"] = parsed is not None
    if parsed is None:
        partial_recovery = recover_partial_pagination_json(response.content or "") if task_name == "analyze_pagination" else None
        if partial_recovery is not None:
            quality["used_partial_recovery"] = True
            parsed = partial_recovery
        else:
            quality["used_repair_pass"] = True
            repaired_payload, repair_response = _attempt_repair_json_payload(
                client,
                response.content or "",
                response_contract,
            )
            audit_event(
                "assist_task_repair_attempt",
                task_name=task_name,
                raw_output=response.content or "",
                repair_response=getattr(repair_response, "content", None),
            )
            if repaired_payload is None:
                combined_usage = response.usage
                if isinstance(response.usage, dict) and isinstance(getattr(repair_response, "usage", None), dict):
                    combined_usage = {
                        key: int(response.usage.get(key, 0)) + int(repair_response.usage.get(key, 0))
                        for key in set(response.usage) | set(repair_response.usage)
                    }
                return _return_with_quality(
                    AssistLlmResponse(
                        success=False,
                        error="Model output was not valid JSON; expected a single JSON object only",
                        raw=response.content,
                        model=repair_response.model or response.model,
                        usage=combined_usage,
                    ),
                    error_code="assist_task_invalid_json",
                )
            parsed = repaired_payload
            if isinstance(response.usage, dict) and isinstance(getattr(repair_response, "usage", None), dict):
                response.usage = {
                    key: int(response.usage.get(key, 0)) + int(repair_response.usage.get(key, 0))
                    for key in set(response.usage) | set(repair_response.usage)
                }
            if getattr(repair_response, "content", None):
                response.content = repair_response.content
            if getattr(repair_response, "model", None):
                response.model = repair_response.model

    normalized = _normalize_assist_json_result(task_name, parsed)
    audit_event(
        "assist_task_normalized",
        task_name=task_name,
        normalized_result=normalized,
        raw_output=response.content or "",
    )

    if is_semantically_empty_pagination_result(task_name, normalized) and has_pagination_evidence(user_prompt):
        quality["semantic_empty_detected"] = True
        heuristic_result = recover_pagination_from_summary(user_prompt)
        if heuristic_result is not None:
            normalized = heuristic_result
            quality["used_heuristic_fallback"] = True
            audit_event("assist_task_heuristic_fallback", task_name=task_name, recovered_result=normalized)
        else:
            quality["used_semantic_retry"] = True
            retried_result, retry_response = _attempt_semantic_retry(
                client,
                user_prompt,
                task_name,
                response_contract,
                response.content or "",
                system_suffix=system_suffix,
            )
            audit_event(
                "assist_task_semantic_retry",
                task_name=task_name,
                retry_response=getattr(retry_response, "content", None),
                retried_result=retried_result,
            )
            if retried_result is not None and not is_semantically_empty_pagination_result(task_name, retried_result):
                normalized = retried_result
                if isinstance(response.usage, dict) and isinstance(getattr(retry_response, "usage", None), dict):
                    response.usage = {
                        key: int(response.usage.get(key, 0)) + int(retry_response.usage.get(key, 0))
                        for key in set(response.usage) | set(retry_response.usage)
                    }
                if getattr(retry_response, "content", None):
                    response.content = retry_response.content
                if getattr(retry_response, "model", None):
                    response.model = retry_response.model
            else:
                audit_event(
                    "assist_task_semantic_failure",
                    task_name=task_name,
                    raw_output=response.content or "",
                    normalized_result=normalized,
                )
                return _return_with_quality(
                    AssistLlmResponse(
                        success=False,
                        error="Pagination analysis returned a semantically empty result despite visible pagination evidence",
                        raw=response.content,
                        model=getattr(retry_response, "model", None) or response.model,
                        usage=response.usage,
                    ),
                    error_code="assist_task_semantic_empty",
                )

    audit_event(
        "assist_task_completed",
        task_name=task_name,
        result=normalized,
        model=response.model,
        usage=response.usage,
    )
    return _return_with_quality(
        AssistLlmResponse(
            success=True,
            result=normalized,
            confidence=float(normalized.get("confidence")) if isinstance(normalized.get("confidence"), (int, float)) else None,
            reason=normalized.get("reason") if isinstance(normalized.get("reason"), str) else None,
            raw=response.content,
            model=response.model,
            usage=response.usage,
        ),
    )


def infer_fields(request: AssistLlmRequest) -> AssistLlmResponse:
    # Truncate HTML to 6000 chars to prevent prompt token explosion on large pages.
    html = (request.html_fragment or "")[:6000]
    prompt = build_field_inference_prompt(html)
    return _run_llm_json_task(prompt, task_name="infer_fields", response_contract=FIELD_INFERENCE_RESPONSE_CONTRACT)


def optimize_selector(request: AssistLlmRequest) -> AssistLlmResponse:
    initial_selector = request.initial_selector or ""
    # Truncate HTML to 6000 chars to keep prompt within budget.
    html = (request.html_fragment or "")[:6000]
    prompt = build_selector_optimization_prompt(initial_selector, html)
    return _run_llm_json_task(prompt, task_name="optimize_selector", response_contract=SELECTOR_OPTIMIZATION_RESPONSE_CONTRACT)


def analyze_pagination(request: AssistLlmRequest) -> AssistLlmResponse:
    # Pass only HTML evidence in user prompt; move analysis rules to system suffix.
    evidence_prompt = build_pagination_analysis_user_prompt(request.html_fragment)
    response = _run_llm_json_task(
        evidence_prompt,
        task_name="analyze_pagination",
        response_contract=PAGINATION_ANALYSIS_RESPONSE_CONTRACT,
        system_suffix=PAGINATION_ANALYSIS_SYSTEM_RULES,
        max_tokens=4000,
    )
    if not response.success or not isinstance(response.result, dict):
        return response

    next_selector = response.result.get("next_button_selector")
    if not isinstance(next_selector, str) or not next_selector.strip():
        return response

    session = _get_live_session_for_selector_validation(request.session_id)
    if session is None:
        return response

    strategy = str(response.result.get("pagination_strategy") or "")
    matched, normalized_selector, validation_reason = _validate_actionable_pagination_selector(session, strategy, next_selector)
    if matched:
        response.result["next_button_selector"] = normalized_selector
        if normalized_selector != next_selector:
            reason = str(response.result.get("reason") or "").strip()
            suffix = "Normalized raw XPath to Playwright query syntax before validating it against the current page."
            response.result["reason"] = f"{reason} {suffix}".strip()
            response.reason = response.result["reason"]
        return response

    fallback = recover_pagination_from_summary(evidence_prompt)
    if fallback:
        fallback_selector = str(fallback.get("next_button_selector") or "").strip()
        fallback_strategy = str(fallback.get("pagination_strategy") or strategy)
        fallback_matched, normalized_fallback, fallback_reason = _validate_actionable_pagination_selector(session, fallback_strategy, fallback_selector)
        if fallback_matched:
            fallback["next_button_selector"] = normalized_fallback
            fallback_reason = str(fallback.get("reason") or "").strip()
            fallback["reason"] = (
                f"{fallback_reason} Replaced the model selector because it was not precise enough for the current page session."
            ).strip()
            response.result = fallback
            response.reason = fallback.get("reason")
            response.confidence = float(fallback.get("confidence")) if isinstance(fallback.get("confidence"), (int, float)) else None
            return response

    return AssistLlmResponse(
        success=True,
        result=response.result,
        confidence=response.confidence,
        reason=response.reason,
        raw=response.raw,
        model=response.model,
        usage=response.usage,
        warnings=[
            f"Pagination analysis produced a candidate selector, but it could not be validated as a single actionable control on the current page session. {validation_reason or 'Review the selector before applying it.'}"
        ],
    )

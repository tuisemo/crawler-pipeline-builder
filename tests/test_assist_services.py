from backend.assist.services import (
    FIELD_INFERENCE_RESPONSE_CONTRACT,
    PAGINATION_ANALYSIS_RESPONSE_CONTRACT,
    _ensure_session,
    analyze_pagination,
    _extract_json_payload,
    _run_llm_json_task,
    extract_html_fragment,
    run_selector_test,
)
from backend.workflow.schemas import AssistHtmlExtractRequest, AssistLlmRequest
from backend.workflow.schemas import AssistLlmResponse, AssistSelectorTestRequest
from backend.llm import LLMResponse


def test_extract_json_payload_recovers_wrapped_balanced_object():
    payload = _extract_json_payload(
        '分析结果如下：\n{"optimized_selector": ".card a", "reason": "stable class", "confidence": 0.91}\n以上。'
    )

    assert payload == {
        "optimized_selector": ".card a",
        "reason": "stable class",
        "confidence": 0.91,
    }


def test_run_llm_json_task_uses_json_object_mode_and_normalizes_fields(monkeypatch):
    captured: dict[str, object] = {}

    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            captured["system"] = system
            captured["user"] = user
            captured["kwargs"] = kwargs
            return LLMResponse(
                content='{"item_selector": ".item", "confidence": 0.88, "reason": "clear repeated cards"}',
                model="fake-model",
                usage={"prompt_tokens": 10, "completion_tokens": 5},
            )

    monkeypatch.setattr("backend.assist.services.get_default_client", lambda: FakeClient())

    response = _run_llm_json_task(
        "Infer fields from this HTML",
        task_name="infer_fields",
        response_contract=FIELD_INFERENCE_RESPONSE_CONTRACT,
    )

    assert response.success is True
    assert response.result == {
        "item_selector": ".item",
        "fields": [],
        "confidence": 0.88,
        "reason": "clear repeated cards",
    }
    assert captured["kwargs"] == {
        "temperature": 0.1,
        "max_tokens": 1500,
        "response_format": {"type": "json_object"},
        "request_name": "assist_infer_fields",
    }
    assert "Return exactly one valid JSON object and nothing else." in str(captured["system"])
    assert '"fields" must always be an array' in str(captured["system"])


def test_analyze_pagination_builds_evidence_package_prompt(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run_llm_json_task(user_prompt: str, task_name: str, response_contract: str, **kwargs):
        captured["user_prompt"] = user_prompt
        captured["task_name"] = task_name
        captured["response_contract"] = response_contract
        captured["kwargs"] = kwargs
        return AssistLlmResponse(
            success=True,
            result={
                "pagination_strategy": "click_next",
                "next_button_selector": 'a[rel="next"]',
                "page_number_selectors": [],
                "item_selector": "",
                "confidence": 0.7,
                "reason": "mock result",
            },
        )

    monkeypatch.setattr("backend.assist.services._run_llm_json_task", fake_run_llm_json_task)

    html_fragment = """<!-- ITEM_SAMPLES -->
<article class="row">item-1</article>
<!-- PAGINATION -->
<div class="kq-pager"><span class="current">1</span><a href="/list?p=2" rel="next">下一页</a></div>
<!-- PAGINATION_CONTROL_SUMMARY -->
[1] | tag=span | text=1 | role_hint=current_page | aria_current=page | class=current
[2] | tag=a | text=下一页 | role_hint=next_candidate | href=/list?p=2 | rel=next | class=next
"""

    result = analyze_pagination(AssistLlmRequest(html_fragment=html_fragment))

    assert result.success is True
    assert captured["task_name"] == "analyze_pagination"
    assert captured["response_contract"] == PAGINATION_ANALYSIS_RESPONSE_CONTRACT
    assert captured["kwargs"]["system_suffix"]
    assert captured["kwargs"]["max_tokens"] == 4000
    assert "## Selection Goal" in str(captured["kwargs"]["system_suffix"])
    assert "### Item Samples" in str(captured["user_prompt"])
    assert "### Pagination HTML Candidate" in str(captured["user_prompt"])
    assert "### Pagination Control Summary" in str(captured["user_prompt"])
    assert "kq-pager" in str(captured["user_prompt"])
    assert "下一页" in str(captured["user_prompt"])


def test_analyze_pagination_normalizes_raw_xpath_selector_when_live_page_matches(monkeypatch):
    class FakePage:
        def query_selector_all(self, selector: str):
            if selector == 'xpath=//a[@rel="next"]':
                return [object()]
            return []

    class FakeSession:
        def __init__(self):
            self.page = FakePage()

        def is_alive(self):
            return True

    def fake_run_llm_json_task(user_prompt: str, task_name: str, response_contract: str, **kwargs):
        return AssistLlmResponse(
            success=True,
            result={
                "pagination_strategy": "click_next",
                "next_button_selector": '//a[@rel="next"]',
                "page_number_selectors": [],
                "item_selector": "",
                "confidence": 0.8,
                "reason": "model result",
            },
        )

    monkeypatch.setattr("backend.assist.services._run_llm_json_task", fake_run_llm_json_task)
    monkeypatch.setattr("backend.assist.services.page_session_mgr.get", lambda session_id: FakeSession())

    response = analyze_pagination(AssistLlmRequest(html_fragment="<!-- PAGINATION --><a rel='next'>下一页</a>", session_id="s1"))

    assert response.success is True
    assert response.result["next_button_selector"] == 'xpath=//a[@rel="next"]'
    assert "Normalized raw XPath" in (response.result["reason"] or "")


def test_analyze_pagination_replaces_unmatched_model_selector_with_summary_fallback(monkeypatch):
    class FakePage:
        def query_selector_all(self, selector: str):
            if selector == 'a[rel="next"]':
                return [object()]
            return []

    class FakeSession:
        def __init__(self):
            self.page = FakePage()

        def is_alive(self):
            return True

    def fake_run_llm_json_task(user_prompt: str, task_name: str, response_contract: str, **kwargs):
        return AssistLlmResponse(
            success=True,
            result={
                "pagination_strategy": "click_next",
                "next_button_selector": ".does-not-match",
                "page_number_selectors": [],
                "item_selector": "",
                "confidence": 0.7,
                "reason": "model result",
            },
        )

    monkeypatch.setattr("backend.assist.services._run_llm_json_task", fake_run_llm_json_task)
    monkeypatch.setattr("backend.assist.services.page_session_mgr.get", lambda session_id: FakeSession())

    html_fragment = """<!-- PAGINATION -->
<div class="kq-pager"><span class="current">1</span><a rel="next" href="/list?p=2">下一页</a></div>
<!-- PAGINATION_CONTROL_SUMMARY -->
[1] | tag=span | text=1 | role_hint=current_page | aria_current=page | class=current
[2] | tag=a | text=下一页 | role_hint=next_candidate | href=/list?p=2 | rel=next | class=next
"""

    response = analyze_pagination(AssistLlmRequest(html_fragment=html_fragment, session_id="s1"))

    assert response.success is True
    assert response.result["next_button_selector"] == 'a[rel="next"]'
    assert "not precise enough for the current page session" in (response.result["reason"] or "")


def test_analyze_pagination_replaces_broad_multi_match_selector_with_summary_fallback(monkeypatch):
    class FakeElement:
        def __init__(self, *, rel: str = "", text: str = "", class_name: str = ""):
            self._rel = rel
            self._text = text
            self._class_name = class_name

        def get_attribute(self, name: str):
            if name == "rel":
                return self._rel
            if name == "class":
                return self._class_name
            return ""

        def inner_text(self):
            return self._text

    class FakePage:
        def query_selector_all(self, selector: str):
            if selector == 'div.kq-pager > a':
                return [
                    FakeElement(text="1", class_name="page-num"),
                    FakeElement(text="2", class_name="page-num"),
                    FakeElement(rel="next", text="下一页", class_name="next"),
                ]
            if selector == 'a[rel="next"]':
                return [FakeElement(rel="next", text="下一页", class_name="next")]
            return []

    class FakeSession:
        def __init__(self):
            self.page = FakePage()

        def is_alive(self):
            return True

    def fake_run_llm_json_task(user_prompt: str, task_name: str, response_contract: str, **kwargs):
        return AssistLlmResponse(
            success=True,
            result={
                "pagination_strategy": "click_next",
                "next_button_selector": "div.kq-pager > a",
                "page_number_selectors": [],
                "item_selector": "",
                "confidence": 0.76,
                "reason": "model result",
            },
        )

    monkeypatch.setattr("backend.assist.services._run_llm_json_task", fake_run_llm_json_task)
    monkeypatch.setattr("backend.assist.services.page_session_mgr.get", lambda session_id: FakeSession())

    html_fragment = """<!-- PAGINATION -->
<div class="kq-pager"><span class="current">1</span><a href="/list?p=2">2</a><a rel="next" href="/list?p=2">下一页</a></div>
<!-- PAGINATION_CONTROL_SUMMARY -->
[1] | tag=span | text=1 | role_hint=current_page | aria_current=page | class=current | parent_tag=div | parent_class=kq-pager
[2] | tag=a | text=2 | role_hint=page_number | class=page-num | parent_tag=div | parent_class=kq-pager
[3] | tag=a | text=下一页 | role_hint=next_candidate | rel=next | class=next | parent_tag=div | parent_class=kq-pager
"""

    response = analyze_pagination(AssistLlmRequest(html_fragment=html_fragment, session_id="s1"))

    assert response.success is True
    assert response.result["next_button_selector"] == 'a[rel="next"]'
    assert "not precise enough for the current page session" in (response.result["reason"] or "")


def test_analyze_pagination_returns_warning_when_selector_cannot_be_validated(monkeypatch):
    class FakePage:
        def query_selector_all(self, selector: str):
            return []

    class FakeSession:
        def __init__(self):
            self.page = FakePage()

        def is_alive(self):
            return True

    def fake_run_llm_json_task(user_prompt: str, task_name: str, response_contract: str, **kwargs):
        return AssistLlmResponse(
            success=True,
            result={
                "pagination_strategy": "click_next",
                "next_button_selector": ".candidate-next",
                "page_number_selectors": [],
                "item_selector": "",
                "confidence": 0.58,
                "reason": "model result",
            },
        )

    monkeypatch.setattr("backend.assist.services._run_llm_json_task", fake_run_llm_json_task)
    monkeypatch.setattr("backend.assist.services.page_session_mgr.get", lambda session_id: FakeSession())
    monkeypatch.setattr("backend.assist.services.recover_pagination_from_summary", lambda user_prompt: None)

    response = analyze_pagination(
        AssistLlmRequest(
            html_fragment="<!-- PAGINATION --><div class='pager'><a class='next'>下一页</a></div>",
            session_id="s1",
        )
    )

    assert response.success is True
    assert response.result["next_button_selector"] == ".candidate-next"
    assert response.warnings
    assert "could not be validated as a single actionable control" in response.warnings[0]


def test_test_selector_highlights_matches_and_returns_session_id(monkeypatch):
    class FakeSession:
        id = "session-1"
        page = object()

    clear_calls: list[object] = []
    highlight_calls: list[tuple[str, int]] = []

    monkeypatch.setattr("backend.assist.services._ensure_session", lambda session_id, url: (FakeSession(), None))
    monkeypatch.setattr(
        "backend.assist.services.SelectorTester.test_selector",
        lambda page, selector, max_samples=5: type("Result", (), {
            "match_count": 3,
            "sample_items": [{"text": "A"}],
            "error": None,
        })(),
    )
    monkeypatch.setattr("backend.assist.services.SelectorTester.clear_selector_highlight", lambda page: clear_calls.append(page))
    monkeypatch.setattr(
        "backend.assist.services.SelectorTester.highlight_selector",
        lambda page, selector, clear_after_ms=2200: highlight_calls.append((selector, clear_after_ms)) or 3,
    )

    response = run_selector_test(
        AssistSelectorTestRequest(
            selector=".item",
            session_id="session-1",
            clear_after_ms=1800,
        )
    )

    assert response.success is True
    assert response.session_id == "session-1"
    assert response.result["match_count"] == 3
    assert response.result["highlighted_count"] == 3
    assert response.result["clear_after_ms"] == 1800
    assert len(clear_calls) == 1
    assert highlight_calls == [(".item", 1800)]


def test_extract_html_fragment_clears_selector_highlight_before_sampling(monkeypatch):
    class FakeSession:
        id = "session-1"
        page = object()

    class FakeExtractor:
        def extract_item_container(self, page, item_selector, max_items=3):
            return type("Result", (), {
                "html": "<div>ok</div>",
                "truncated": False,
                "original_size": 13,
                "truncated_size": 13,
                "item_count": 1,
            })()

    clear_calls: list[object] = []

    monkeypatch.setattr("backend.assist.services._ensure_session", lambda session_id, url: (FakeSession(), None))
    monkeypatch.setattr("backend.assist.services.SelectorTester.clear_selector_highlight", lambda page: clear_calls.append(page))
    monkeypatch.setattr("backend.assist.services.HtmlExtractor", lambda: FakeExtractor())

    response = extract_html_fragment(AssistHtmlExtractRequest(item_selector=".item"))

    assert response.success is True
    assert response.html_fragment == "<div>ok</div>"
    assert len(clear_calls) == 1


def test_run_llm_json_task_reports_invalid_json_when_unrecoverable(monkeypatch):
    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            return LLMResponse(
                content='{"optimized_selector": ".item", "reason": "missing closing brace"',
                model="fake-model",
            )

    monkeypatch.setattr("backend.assist.services.get_default_client", lambda: FakeClient())

    response = _run_llm_json_task(
        "Optimize selector",
        task_name="optimize_selector",
        response_contract="Return optimized_selector JSON only.",
    )

    assert response.success is False
    assert response.error == "Model output was not valid JSON; expected a single JSON object only"
    assert '"optimized_selector": ".item"' in (response.raw or "")


def test_run_llm_json_task_repairs_invalid_json_with_second_pass(monkeypatch):
    captured_calls: list[dict[str, object]] = []

    class FakeClient:
        def __init__(self):
            self.call_count = 0

        def generate_with_system(self, system: str, user: str, **kwargs):
            self.call_count += 1
            captured_calls.append({"system": system, "user": user, "kwargs": kwargs})
            if self.call_count == 1:
                return LLMResponse(
                    content='```json\n{"optimized_selector": ".item", "confidence": 0.8,\n```',
                    model="fake-model",
                    usage={"prompt_tokens": 8, "completion_tokens": 4},
                )
            return LLMResponse(
                content='{"optimized_selector": ".item", "confidence": 0.8, "reason": "repaired"}',
                model="fake-model",
                usage={"prompt_tokens": 4, "completion_tokens": 3},
            )

    monkeypatch.setattr("backend.assist.services.get_default_client", lambda: FakeClient())

    response = _run_llm_json_task(
        "Optimize selector",
        task_name="optimize_selector",
        response_contract="Return optimized_selector JSON only.",
    )

    assert response.success is True
    assert response.result == {
        "optimized_selector": ".item",
        "confidence": 0.8,
        "reason": "repaired",
    }
    assert response.usage == {"prompt_tokens": 12, "completion_tokens": 7}
    assert len(captured_calls) == 2
    assert "JSON repair utility" in str(captured_calls[1]["system"])


def test_run_llm_json_task_uses_heuristic_fallback_for_empty_pagination_result(monkeypatch):
    html_prompt = """HTML:
<!-- PAGINATION -->
<div class="kq-pager"><span class="current">1</span><a href="/list?p=2">2</a><a class="next" rel="next" href="/list?p=2">下一页</a></div>
<!-- PAGINATION_CONTROL_SUMMARY -->
[1] | tag=span | text=1 | role_hint=current_page | aria_current=page | class=current
[2] | tag=a | text=2 | role_hint=page_number | href=/list?p=2 | class=page-num
[3] | tag=a | text=下一页 | role_hint=next_candidate | href=/list?p=2 | rel=next | class=next
"""

    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            return LLMResponse(
                content='{"pagination_strategy":"none","next_button_selector":"","page_number_selectors":[],"item_selector":"","confidence":0.0,"reason":"No raw model output provided; using defaults."}',
                model="fake-model",
                usage={"prompt_tokens": 7, "completion_tokens": 4},
            )

    monkeypatch.setattr("backend.assist.services.get_default_client", lambda: FakeClient())

    response = _run_llm_json_task(
        html_prompt,
        task_name="analyze_pagination",
        response_contract=PAGINATION_ANALYSIS_RESPONSE_CONTRACT,
    )

    assert response.success is True
    assert response.result["pagination_strategy"] == "click_next"
    assert response.result["next_button_selector"] == 'a[rel="next"]'
    assert response.result["confidence"] == 0.56
    assert "Recovered from pagination control summary" in (response.result["reason"] or "")


def test_run_llm_json_task_uses_heuristic_fallback_for_heading_style_pagination_summary(monkeypatch):
    prompt = """Given HTML content containing pagination elements, analyze the pagination pattern and extract highly robust selectors.

HTML:
## Selection Goal
Identify the concrete control that advances pagination.

## Evidence Package
### Item Samples
<article class="row">item-1</article>

### Pagination HTML Candidate
<div class="kq-pager"><span class="current">1</span><a class="next" rel="next" href="/list?p=2">下一页</a></div>

### Pagination Control Summary
[1] | tag=span | text=1 | role_hint=current_page | aria_current=page | class=current
[2] | tag=a | text=下一页 | role_hint=next_candidate | href=/list?p=2 | rel=next | class=next

## Decision Policy
- Prefer semantic evidence.
"""

    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            return LLMResponse(
                content='{"pagination_strategy":"none","next_button_selector":"","page_number_selectors":[],"item_selector":"","confidence":0.0,"reason":""}',
                model="fake-model",
                usage={"prompt_tokens": 7, "completion_tokens": 4},
            )

    monkeypatch.setattr("backend.assist.services.get_default_client", lambda: FakeClient())

    response = _run_llm_json_task(
        prompt,
        task_name="analyze_pagination",
        response_contract=PAGINATION_ANALYSIS_RESPONSE_CONTRACT,
    )

    assert response.success is True
    assert response.result["pagination_strategy"] == "click_next"
    assert response.result["next_button_selector"] == 'a[rel="next"]'


def test_run_llm_json_task_uses_parent_class_hint_for_next_arrow_summary(monkeypatch):
    prompt = """HTML:
<!-- PAGINATION -->
<ul class="pager"><li class="next"><a href="/page/2/">Next <span aria-hidden="true">→</span></a></li></ul>
<!-- PAGINATION_CONTROL_SUMMARY -->
[1] | tag=a | text=Next → | role_hint=next_candidate | href=/page/2/ | parent_tag=li | parent_class=next
"""

    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            return LLMResponse(
                content='{"pagination_strategy":"none","next_button_selector":"","page_number_selectors":[],"item_selector":"","confidence":0.0,"reason":""}',
                model="fake-model",
                usage={"prompt_tokens": 7, "completion_tokens": 4},
            )

    monkeypatch.setattr("backend.assist.services.get_default_client", lambda: FakeClient())

    response = _run_llm_json_task(
        prompt,
        task_name="analyze_pagination",
        response_contract=PAGINATION_ANALYSIS_RESPONSE_CONTRACT,
    )

    assert response.success is True
    assert response.result["pagination_strategy"] == "click_next"
    assert response.result["next_button_selector"] == "li.next > a"


def test_run_llm_json_task_rejects_empty_pagination_result_when_retry_still_empty(monkeypatch):
    html_prompt = """HTML:
<!-- PAGINATION -->
<div class="pager"><a href="/list?p=2">下一页</a></div>
<!-- PAGINATION_CONTROL_SUMMARY -->
[1] | tag=a | text=下一页 | role_hint=next_candidate | href=/list?p=2
"""

    class FakeClient:
        def __init__(self):
            self.call_count = 0

        def generate_with_system(self, system: str, user: str, **kwargs):
            self.call_count += 1
            return LLMResponse(
                content='{"pagination_strategy":"none","next_button_selector":"","page_number_selectors":[],"item_selector":"","confidence":0.0,"reason":""}',
                model="fake-model",
                usage={"prompt_tokens": 5, "completion_tokens": 3},
            )

    monkeypatch.setattr("backend.assist.services.get_default_client", lambda: FakeClient())

    response = _run_llm_json_task(
        html_prompt,
        task_name="analyze_pagination",
        response_contract=PAGINATION_ANALYSIS_RESPONSE_CONTRACT,
    )

    assert response.success is False
    assert response.error == "Pagination analysis returned a semantically empty result despite visible pagination evidence"


def test_run_llm_json_task_recovers_truncated_pagination_json(monkeypatch):
    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            return LLMResponse(
                content='{\n  "pagination_strategy": "click_next",\n  "next_button_selector": ".next",\n  "page_number_selectors": [\n    "a[href*=\\\'p=\\\']"\n',
                model="fake-model",
                usage={"prompt_tokens": 12, "completion_tokens": 9},
            )

    monkeypatch.setattr("backend.assist.services.get_default_client", lambda: FakeClient())

    response = _run_llm_json_task(
        "<!-- PAGINATION --><div class='pager'></div>",
        task_name="analyze_pagination",
        response_contract=PAGINATION_ANALYSIS_RESPONSE_CONTRACT,
    )

    assert response.success is True
    assert response.result["pagination_strategy"] == "click_next"
    assert response.result["next_button_selector"] == ".next"
    assert response.result["page_number_selectors"] == ["a[href*='p=']"]
    assert response.result["reason"] == "Recovered from truncated JSON output."


def test_ensure_session_creates_fresh_session_for_url_without_explicit_session_id(monkeypatch):
    created = []

    class FakeSession:
        def __init__(self, session_id: str):
            self.id = session_id
            self.navigated_to = None

        def is_alive(self):
            return True

        def navigate(self, url: str, timeout: int = 30000):
            self.navigated_to = (url, timeout)

    active_session = FakeSession("active-1")
    created_session = FakeSession("created-1")

    class FakeManager:
        def create(self):
            created.append(True)
            return created_session

    monkeypatch.setattr("backend.assist.services.get_active_session", lambda: active_session)
    monkeypatch.setattr("backend.assist.services.page_session_mgr", FakeManager())

    session, error = _ensure_session(None, "https://example.com/list")

    assert error is None
    assert session is created_session
    assert created == [True]
    assert session.navigated_to == ("https://example.com/list", 30000)

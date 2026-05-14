from backend.assist.services import (
    FIELD_INFERENCE_RESPONSE_CONTRACT,
    PAGINATION_ANALYSIS_RESPONSE_CONTRACT,
    analyze_pagination,
    _extract_json_payload,
    _run_llm_json_task,
)
from backend.workflow.schemas import AssistLlmRequest
from backend.workflow.schemas import AssistLlmResponse
from backend.llm import LLMResponse
from backend.llm.client import OpenAIClient


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
        "response_format": {"type": "json_object"},
        "request_name": "assist_infer_fields",
    }
    assert "Return exactly one valid JSON object and nothing else." in str(captured["system"])
    assert '"fields" must always be an array' in str(captured["system"])


def test_openai_client_generate_with_system_strips_internal_request_kwargs(monkeypatch):
    captured: dict[str, object] = {}

    def fake_call_api(self, messages, method, request_id, request_name, **kwargs):
        captured["messages"] = messages
        captured["method"] = method
        captured["request_id"] = request_id
        captured["request_name"] = request_name
        captured["kwargs"] = kwargs
        return LLMResponse(content='{"ok":true}', model="fake-model")

    monkeypatch.setattr(OpenAIClient, "_call_api", fake_call_api)

    client = OpenAIClient(api_key="test-key", base_url="https://example.com", model="test-model")
    response = client.generate_with_system(
        "system prompt",
        "user prompt",
        request_id="req-123",
        request_name="assist_infer_fields",
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    assert response.error is None
    assert captured["method"] == "generate_with_system"
    assert captured["request_id"] == "req-123"
    assert captured["request_name"] == "assist_infer_fields"
    assert captured["kwargs"] == {
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }


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
    assert "## Selection Goal" in str(captured["kwargs"]["system_suffix"])
    assert "### Item Samples" in str(captured["user_prompt"])
    assert "### Pagination HTML Candidate" in str(captured["user_prompt"])
    assert "### Pagination Control Summary" in str(captured["user_prompt"])
    assert "kq-pager" in str(captured["user_prompt"])
    assert "下一页" in str(captured["user_prompt"])


def test_analyze_pagination_passes_model_selector_through_without_live_validation(monkeypatch):
    def fake_run_llm_json_task(user_prompt: str, task_name: str, response_contract: str, **kwargs):
        return AssistLlmResponse(
            success=True,
            result={
                "pagination_strategy": "click_next",
                "next_button_selector": '//a[@rel="next"]',
                "page_number_selectors": [],
                "confidence": 0.8,
                "reason": "model result",
            },
        )

    monkeypatch.setattr("backend.assist.services._run_llm_json_task", fake_run_llm_json_task)

    response = analyze_pagination(AssistLlmRequest(html_fragment="<!-- PAGINATION --><a rel='next'>下一页</a>"))

    assert response.success is True
    assert response.result["next_button_selector"] == '//a[@rel="next"]'
    assert response.reason is None
    assert response.warnings == []


def test_analyze_pagination_filters_non_string_page_number_selectors(monkeypatch):
    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            return LLMResponse(
                content='{"pagination_strategy":"click_next","next_button_selector":"a.next","page_number_selectors":[".page",3,null,""],"confidence":0.8,"reason":"model result"}',
                model="fake-model",
                usage={"prompt_tokens": 8, "completion_tokens": 4},
            )

    monkeypatch.setattr("backend.assist.services.get_default_client", lambda: FakeClient())

    response = _run_llm_json_task(
        "<!-- PAGINATION --><a class='next'>下一页</a>",
        task_name="analyze_pagination",
        response_contract=PAGINATION_ANALYSIS_RESPONSE_CONTRACT,
    )

    assert response.success is True
    assert response.result["page_number_selectors"] == [".page"]


def test_analyze_pagination_builds_evidence_from_structured_request_fields(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run_llm_json_task(user_prompt: str, task_name: str, response_contract: str, **kwargs):
        captured["user_prompt"] = user_prompt
        return AssistLlmResponse(
            success=True,
            result={
                "pagination_strategy": "click_next",
                "next_button_selector": "a.next",
                "page_number_selectors": [],
                "confidence": 0.73,
                "reason": "model result",
            },
        )

    monkeypatch.setattr("backend.assist.services._run_llm_json_task", fake_run_llm_json_task)

    response = analyze_pagination(
        AssistLlmRequest(
            html_fragment="<article class='row'>item-1</article>",
            pagination_component_html="<div class='pager'><a class='next'>下一页</a></div>",
            pruned_body_html="<main><div class='pager'><a class='next'>下一页</a></div></main>",
        )
    )

    assert response.success is True
    assert "### Item Samples" in str(captured["user_prompt"])
    assert "### Pagination HTML Candidate" in str(captured["user_prompt"])
    assert "### Global Pruned Body" in str(captured["user_prompt"])
    assert "下一页" in str(captured["user_prompt"])


def test_analyze_pagination_merges_missing_structured_sections(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run_llm_json_task(user_prompt: str, task_name: str, response_contract: str, **kwargs):
        captured["user_prompt"] = user_prompt
        return AssistLlmResponse(
            success=True,
            result={
                "pagination_strategy": "click_next",
                "next_button_selector": "a.next",
                "page_number_selectors": [],
                "confidence": 0.73,
                "reason": "model result",
            },
        )

    monkeypatch.setattr("backend.assist.services._run_llm_json_task", fake_run_llm_json_task)

    response = analyze_pagination(
        AssistLlmRequest(
            html_fragment="<!-- ITEM_SAMPLES -->\n<article class='row'>item-1</article>",
            pagination_component_html="<div class='pager'><a class='next'>下一页</a></div>",
            pruned_body_html="<main><div class='pager'><a class='next'>下一页</a></div></main>",
        )
    )

    assert response.success is True
    assert "### Item Samples" in str(captured["user_prompt"])
    assert "### Pagination HTML Candidate" in str(captured["user_prompt"])
    assert "### Global Pruned Body" in str(captured["user_prompt"])


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
                content='{"pagination_strategy":"none","next_button_selector":"","page_number_selectors":[],"confidence":0.0,"reason":"No raw model output provided; using defaults."}',
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
    assert response.result["next_button_selector"] == 'a.next[rel="next"]'
    assert response.result["page_number_selectors"] == []
    assert response.result["confidence"] == 0.56
    assert "Recovered from pagination control summary" in (response.result["reason"] or "")


def test_run_llm_json_task_allows_legitimate_none_pagination_result_without_evidence(monkeypatch):
    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            return LLMResponse(
                content='{"pagination_strategy":"none","next_button_selector":"","page_number_selectors":[],"confidence":0.0,"reason":"No pagination found."}',
                model="fake-model",
                usage={"prompt_tokens": 7, "completion_tokens": 4},
            )

    monkeypatch.setattr("backend.assist.services.get_default_client", lambda: FakeClient())

    response = _run_llm_json_task(
        "<article>single page content</article>",
        task_name="analyze_pagination",
        response_contract=PAGINATION_ANALYSIS_RESPONSE_CONTRACT,
    )

    assert response.success is True
    assert response.result["pagination_strategy"] == "none"
    assert response.result["next_button_selector"] == ""
    assert response.result["page_number_selectors"] == []


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
                content='{"pagination_strategy":"none","next_button_selector":"","page_number_selectors":[],"confidence":0.0,"reason":""}',
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
    assert response.result["next_button_selector"] == 'a.next[rel="next"]'


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
                content='{"pagination_strategy":"none","next_button_selector":"","page_number_selectors":[],"confidence":0.0,"reason":""}',
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


def test_run_llm_json_task_scopes_next_like_class_when_parent_context_exists(monkeypatch):
    prompt = """HTML:
<!-- PAGINATION -->
<ul class="pager"><li class="pager-item"><a class="next" href="/page/2/">Next</a></li></ul>
<!-- PAGINATION_CONTROL_SUMMARY -->
[1] | tag=a | text=Next | role_hint=next_candidate | href=/page/2/ | class=next | parent_tag=li | parent_class=pager-item
"""

    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            return LLMResponse(
                content='{"pagination_strategy":"none","next_button_selector":"","page_number_selectors":[],"confidence":0.0,"reason":""}',
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
    assert response.result["next_button_selector"] == "li.pager-item > a.next"


def test_run_llm_json_task_uses_scoped_xpath_for_generic_pager_text_match(monkeypatch):
    prompt = """HTML:
<!-- PAGINATION -->
<div class="pagination"><a href="/list?p=2">下一页</a></div>
<!-- PAGINATION_CONTROL_SUMMARY -->
[1] | tag=a | text=下一页 | role_hint=next_candidate | href=/list?p=2 | parent_tag=div | parent_class=pagination
"""

    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            return LLMResponse(
                content='{"pagination_strategy":"none","next_button_selector":"","page_number_selectors":[],"confidence":0.0,"reason":""}',
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
    assert response.result["next_button_selector"] == '//div[contains(concat(\' \', normalize-space(@class), \' \'), " pagination ")]//a[contains(normalize-space(string(.)), "下一页")]'


def test_run_llm_json_task_scopes_page_number_selectors_with_parent_context(monkeypatch):
    prompt = """HTML:
<!-- PAGINATION -->
<ul class="pager"><li><a class="page-num" href="/list?p=1">1</a></li><li><a class="page-num" href="/list?p=2">2</a></li><li class="next"><a href="/list?p=2">下一页</a></li></ul>
<!-- PAGINATION_CONTROL_SUMMARY -->
[1] | tag=a | text=1 | role_hint=page_number | href=/list?p=1 | class=page-num | parent_tag=li | parent_class=pager
[2] | tag=a | text=2 | role_hint=page_number | href=/list?p=2 | class=page-num | parent_tag=li | parent_class=pager
[3] | tag=a | text=下一页 | role_hint=next_candidate | href=/list?p=2 | parent_tag=li | parent_class=next
"""

    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            return LLMResponse(
                content='{"pagination_strategy":"none","next_button_selector":"","page_number_selectors":[],"confidence":0.0,"reason":""}',
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
    assert response.result["page_number_selectors"] == ["li.pager > a.page-num"]


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
                content='{"pagination_strategy":"none","next_button_selector":"","page_number_selectors":[],"confidence":0.0,"reason":""}',
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


def test_run_llm_json_task_recovers_truncated_pagination_json_with_unicode_selector(monkeypatch):
    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            return LLMResponse(
                content='{"pagination_strategy":"click_next","next_button_selector":"//a[contains(text(), \\"下一页\\")]","page_number_selectors":[',
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
    assert response.result["next_button_selector"] == '//a[contains(text(), "下一页")]'
    assert response.result["reason"] == "Recovered from truncated JSON output."


def test_run_llm_json_task_recovers_closed_page_selector_array_without_leaking_later_fields(monkeypatch):
    class FakeClient:
        def generate_with_system(self, system: str, user: str, **kwargs):
            return LLMResponse(
                content='{"pagination_strategy":"click_next","next_button_selector":".next","page_number_selectors":[".page-link"],"reason":"truncated',
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
    assert response.result["page_number_selectors"] == [".page-link"]
    assert "reason" not in response.result["page_number_selectors"]



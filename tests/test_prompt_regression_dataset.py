import json
from pathlib import Path

from backend.assist_services import _run_llm_json_task
from llm_client import LLMResponse


def _load_cases() -> list[dict]:
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "prompt_regression_cases.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def test_prompt_regression_cases_are_stable(monkeypatch):
    cases = _load_cases()

    for case in cases:
        class FakeClient:
            def generate_with_system(self, system: str, user: str, **kwargs):
                return LLMResponse(
                    content=case["model_output"],
                    model="fake-model",
                    usage={"prompt_tokens": 10, "completion_tokens": 6},
                )

        monkeypatch.setattr("backend.assist_services.get_default_client", lambda: FakeClient())
        response = _run_llm_json_task(
            case["user_prompt"],
            task_name=case["task_name"],
            response_contract=case["response_contract"],
        )

        assert response.success is case["expected_success"], case["name"]

        if "expected_result" in case:
            assert response.result == case["expected_result"], case["name"]
        if "expected_result_subset" in case:
            subset = case["expected_result_subset"]
            assert isinstance(response.result, dict), case["name"]
            for key, expected_value in subset.items():
                assert response.result.get(key) == expected_value, case["name"]


def test_assist_prompt_quality_metric_marks_repair_path(monkeypatch):
    events: list[dict] = []

    def fake_audit_event(event_type: str, **payload):
        events.append({"event_type": event_type, **payload})

    class FakeClient:
        def __init__(self):
            self.call_count = 0

        def generate_with_system(self, system: str, user: str, **kwargs):
            self.call_count += 1
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

    monkeypatch.setattr("backend.assist_services.audit_event", fake_audit_event)
    monkeypatch.setattr("backend.assist_services.get_default_client", lambda: FakeClient())

    response = _run_llm_json_task(
        "Optimize selector",
        task_name="optimize_selector",
        response_contract="Return optimized_selector JSON only.",
    )

    assert response.success is True
    metric_events = [event for event in events if event.get("event_type") == "assist_prompt_quality_metric"]
    assert len(metric_events) == 1
    metric = metric_events[0]
    assert metric["success"] is True
    assert metric["used_repair_pass"] is True
    assert metric["json_valid_first_pass"] is False

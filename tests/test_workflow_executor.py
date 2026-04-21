import pytest

from backend.workflow_executor import WorkflowExecutor
from backend.workflow_schemas import TestSubflowRequest


class FakeElement:
    def __init__(self, text="", html="", attrs=None, children=None):
        self._text = text
        self._html = html
        self._attrs = attrs or {}
        self._children = children or {}

    def inner_text(self):
        return self._text

    def text_content(self):
        return self._text

    def inner_html(self):
        return self._html

    def get_attribute(self, name):
        return self._attrs.get(name)

    def query_selector_all(self, selector):
        if selector == "*":
            return [child for values in self._children.values() for child in values]
        if selector == "img":
            return self._children.get("img", [])
        if selector == "a[href]":
            return self._children.get("a[href]", []) or self._children.get("a", [])
        return self._children.get(selector, [])


class FakePage:
    def __init__(self):
        self.url = "http://example.com/base/"
        self._selectors = {}

    def query_selector_all(self, selector):
        if selector == "bad[":
            raise ValueError("invalid selector")
        return self._selectors.get(selector, [])


class FakeSession:
    def __init__(self):
        self.page = FakePage()
        self.navigated = []

    def navigate(self, url, timeout=30000):
        self.navigated.append((url, timeout))
        self.page.url = url


def graph(nodes, edges):
    return {"nodes": nodes, "edges": edges}


def node(node_id, node_type, data=None):
    return {"id": node_id, "type": node_type, "data": data or {}}


@pytest.mark.anyio
async def test_subflow_runtime_returns_structured_logs_and_results(monkeypatch):
    session = FakeSession()
    title = FakeElement(text="First title")
    link = FakeElement(text="Read", attrs={"href": "/detail"})
    tag_one = FakeElement(text="alpha", attrs={"href": "/tags/a"})
    tag_two = FakeElement(text="beta", attrs={"href": "/tags/b"})
    item = FakeElement(
        text="First item",
        html="<h2>First title</h2><a href='/detail'>Read</a>",
        children={"h2": [title], "a": [link], ".tag": [tag_one, tag_two], "a[href]": [link]},
    )
    session.page._selectors[".item"] = [item]
    monkeypatch.setattr("backend.workflow_executor.page_session_mgr.create", lambda: session)

    request = TestSubflowRequest.model_validate({
        "graph": graph(
            [
                node("open", "open_page", {"url": "http://example.com/list"}),
                node("list", "select_list", {"item_selector": ".item"}),
                node("extract", "extract_field", {"fields": [
                    {"name": "title", "selector": "h2", "type": "text"},
                    {"name": "link", "selector": "a", "type": "attr:href:abs"},
                    {"name": "tags", "selector": ".tag", "type": "all(text)"},
                    {"name": "missing", "selector": ".missing", "type": "text"},
                ]}),
            ],
            [
                {"id": "e1", "source": "open", "target": "list"},
                {"id": "e2", "source": "list", "target": "extract"},
            ],
        ),
        "boundary": {"max_items": 1, "max_steps": 5},
    })

    response = await WorkflowExecutor().test_subflow(request)

    assert response.success is True
    assert response.steps_executed == 3
    assert response.logs
    assert {log.level.value for log in response.logs} <= {"debug", "info", "warning", "error"}
    assert any(log.node_id == "list" for log in response.logs)
    assert [result.node_id for result in response.node_results] == ["open", "list", "extract"]
    assert all(result.started_at <= result.completed_at for result in response.node_results)
    list_result = response.node_results[1].result
    assert list_result["match_count"] == 1
    assert list_result["samples"][0]["text"] == "First item"
    assert list_result["samples"][0]["children"] >= 1
    record = response.records[0]
    assert record == {
        "_index": 0,
        "title": "First title",
        "link": "http://example.com/detail",
        "tags": ["alpha", "beta"],
        "missing": None,
    }


@pytest.mark.anyio
async def test_subflow_step_limit_returns_partial_structured_failure(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr("backend.workflow_executor.page_session_mgr.create", lambda: session)

    request = TestSubflowRequest.model_validate({
        "graph": graph(
            [
                node("open", "open_page", {"url": "http://example.com"}),
                node("loop", "select_list", {"item_selector": ".missing"}),
                node("loop2", "select_list", {"item_selector": ".missing"}),
            ],
            [
                {"id": "e1", "source": "open", "target": "loop"},
                {"id": "e2", "source": "open", "target": "loop2"},
                {"id": "e3", "source": "loop2", "target": "open"},
            ],
        ),
        "boundary": {"max_steps": 1, "max_items": 1},
    })

    response = await WorkflowExecutor().test_subflow(request)

    assert response.success is False
    assert response.partial is True
    assert response.steps_executed == 1
    assert "Max steps" in response.error
    assert response.node_results[0].node_id == "open"
    assert response.logs[-1].level.value == "warning"

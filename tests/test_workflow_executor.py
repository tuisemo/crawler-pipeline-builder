import pytest
import sqlite3
from pathlib import Path

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
async def test_subflow_uses_node_limit_when_boundary_omitted(monkeypatch):
    session = FakeSession()
    session.page._selectors[".item"] = [FakeElement(text=f"Item {idx}") for idx in range(5)]
    monkeypatch.setattr("backend.workflow_executor.page_session_mgr.create", lambda: session)

    request = TestSubflowRequest.model_validate({
        "graph": graph(
            [
                node("open", "open_page", {"url": "http://example.com/list"}),
                node("list", "select_list", {"item_selector": ".item", "max_items": 2}),
            ],
            [{"id": "e1", "source": "open", "target": "list"}],
        ),
    })

    response = await WorkflowExecutor().test_subflow(request)

    assert response.success is True
    assert len(response.node_results[1].result["samples"]) == 2


@pytest.mark.anyio
async def test_subflow_boundary_limit_overrides_node_limit(monkeypatch):
    session = FakeSession()
    session.page._selectors[".item"] = [FakeElement(text=f"Item {idx}") for idx in range(5)]
    monkeypatch.setattr("backend.workflow_executor.page_session_mgr.create", lambda: session)

    request = TestSubflowRequest.model_validate({
        "graph": graph(
            [
                node("open", "open_page", {"url": "http://example.com/list"}),
                node("list", "select_list", {"item_selector": ".item", "max_items": 4}),
            ],
            [{"id": "e1", "source": "open", "target": "list"}],
        ),
        "boundary": {"max_items": 2},
    })

    response = await WorkflowExecutor().test_subflow(request)

    assert response.success is True
    assert len(response.node_results[1].result["samples"]) == 2


@pytest.mark.anyio
async def test_test_node_uses_target_node_limit_when_request_limit_omitted(monkeypatch):
    from backend.workflow_schemas import TestNodeRequest

    session = FakeSession()
    session.page._selectors[".item"] = [FakeElement(text=f"Item {idx}") for idx in range(5)]
    monkeypatch.setattr("backend.workflow_executor.page_session_mgr.create", lambda: session)

    request = TestNodeRequest.model_validate({
        "graph": graph(
            [
                node("open", "open_page", {"url": "http://example.com/list"}),
                node("list", "select_list", {"item_selector": ".item", "max_items": 2}),
            ],
            [{"id": "e1", "source": "open", "target": "list"}],
        ),
        "node_id": "list",
    })

    response = await WorkflowExecutor().test_node(request)

    assert response.success is True
    assert len(response.result.result["samples"]) == 2


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

@pytest.mark.anyio
async def test_subflow_revisit_cycle_stops_when_state_does_not_advance(monkeypatch):
    session = FakeSession()
    session.page._selectors[".item"] = [FakeElement(text="One")]
    monkeypatch.setattr("backend.workflow_executor.page_session_mgr.create", lambda: session)

    request = TestSubflowRequest.model_validate({
        "graph": graph(
            [
                node("open", "open_page", {"url": "http://example.com/list"}),
                node("list", "select_list", {"item_selector": ".item"}),
                node("extract", "extract_field", {"fields": [{"name": "title", "selector": ".", "type": "text"}]}),
            ],
            [
                {"id": "e1", "source": "open", "target": "list"},
                {"id": "e2", "source": "list", "target": "extract"},
                {"id": "e3", "source": "extract", "target": "list"},
            ],
        ),
        "boundary": {"max_items": 1, "max_steps": 10},
    })

    response = await WorkflowExecutor().test_subflow(request)

    assert response.success is True
    assert response.partial is False
    assert response.steps_executed < 10
    assert [result.node_id for result in response.node_results] == ["open", "list", "extract", "list", "extract"]
    assert any("Skipped revisit" in log.message for log in response.logs)


@pytest.mark.anyio
async def test_subflow_executes_emit_record_and_paginate_smoke(monkeypatch):
    session = FakeSession()
    item_one = FakeElement(text="One", children={".name": [FakeElement(text="One")], "*": [FakeElement(text="One")]})
    item_two = FakeElement(text="Two", children={".name": [FakeElement(text="Two")], "*": [FakeElement(text="Two")]})
    session.page._selectors[".item"] = [item_one, item_two]
    session.page._selectors["a.next"] = [FakeElement(text="Next")]
    monkeypatch.setattr("backend.workflow_executor.page_session_mgr.create", lambda: session)

    request = TestSubflowRequest.model_validate({
        "graph": graph(
            [
                node("open", "open_page", {"url": "http://example.com/list"}),
                node("list", "select_list", {"item_selector": ".item"}),
                node("extract", "extract_field", {"fields": [{"name": "name", "selector": ".name", "type": "text"}]}),
                node("emit", "emit_record"),
                node("page", "paginate", {"pagination_selector": "a.next", "pagination_strategy": "click_next"}),
            ],
            [
                {"id": "e1", "source": "open", "target": "list"},
                {"id": "e2", "source": "list", "target": "extract"},
                {"id": "e3", "source": "extract", "target": "emit"},
                {"id": "e4", "source": "emit", "target": "page"},
            ],
        ),
        "boundary": {"max_items": 1, "max_steps": 10},
    })

    response = await WorkflowExecutor().test_subflow(request)

    assert response.success is True
    assert [result.node_id for result in response.node_results] == ["open", "list", "extract", "emit", "page"]
    assert response.records == [{"_index": 0, "name": "One"}]
    assert response.node_results[3].result == {"emitted_count": 1, "records": [{"_index": 0, "name": "One"}]}
    assert response.node_results[4].result["found"] is True
    assert "single-page testing" in response.node_results[4].result["message"]


@pytest.mark.anyio
async def test_subflow_emit_record_can_persist_sqlite(monkeypatch):
    workspace_root = Path(__file__).resolve().parent / ".tmp" / "executor-emit-sqlite"
    if workspace_root.exists():
        for child in sorted(workspace_root.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        workspace_root.rmdir()
    workspace_root.mkdir(parents=True, exist_ok=True)

    session = FakeSession()
    item_one = FakeElement(text="One", children={".name": [FakeElement(text="One")], ".detail": [FakeElement(text="https://example.com/p/1")]})
    session.page._selectors[".item"] = [item_one]
    monkeypatch.setattr("backend.workflow_executor.page_session_mgr.create", lambda: session)
    monkeypatch.setattr("backend.record_sinks.WORKSPACE_ROOT", workspace_root)

    request = TestSubflowRequest.model_validate({
        "graph": graph(
            [
                node("open", "open_page", {"url": "http://example.com/list"}),
                node("list", "select_list", {"item_selector": ".item"}),
                node("extract", "extract_field", {"fields": [
                    {"name": "name", "selector": ".name", "type": "text"},
                    {"name": "detail_url", "selector": ".detail", "type": "text"},
                ]}),
                node("emit", "emit_record", {
                    "output_mode": "sqlite",
                    "sqlite_path": "output/runtime.db",
                    "sqlite_table": "records",
                    "write_mode": "upsert",
                    "dedupe_keys": ["detail_url"],
                }),
            ],
            [
                {"id": "e1", "source": "open", "target": "list"},
                {"id": "e2", "source": "list", "target": "extract"},
                {"id": "e3", "source": "extract", "target": "emit"},
            ],
        ),
        "boundary": {"max_items": 5, "max_steps": 10},
    })

    response = await WorkflowExecutor().test_subflow(request)

    assert response.success is True
    emit_result = response.node_results[-1].result
    assert emit_result["output_mode"] == "sqlite"
    db_path = workspace_root / "output" / "runtime.db"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT name, detail_url FROM records").fetchone()
    assert row == ("One", "https://example.com/p/1")


@pytest.mark.anyio
async def test_runtime_reports_required_data_and_unsupported_nodes(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr("backend.workflow_executor.page_session_mgr.create", lambda: session)

    cases = [
        (node("list", "select_list"), "item_selector is required"),
        (node("extract", "extract_field"), "fields are required"),
        (node("page", "paginate"), "pagination_selector is required"),
        (node("condition", "condition"), "condition field is required"),
        (node("custom", "custom_detail"), "Unsupported node type: custom_detail"),
    ]

    for test_node, expected_error in cases:
        request = TestSubflowRequest.model_validate({
            "graph": graph([node("open", "open_page", {"url": "http://example.com"}), test_node], [{"id": "e", "source": "open", "target": test_node["id"]}]),
            "boundary": {"start_node_id": test_node["id"], "max_steps": 2},
        })

        response = await WorkflowExecutor().test_subflow(request)

        assert response.success is False
        failed_result = response.node_results[-1]
        assert failed_result.success is False
        assert expected_error in failed_result.error
        if expected_error.startswith("Unsupported"):
            assert failed_result.result["status"] == "unsupported"
            assert response.logs[-1].level.value == "error"


@pytest.mark.anyio
async def test_loop_and_end_nodes_are_supported(monkeypatch):
    """loop and end nodes are now supported (no-op / context-setting)."""
    session = FakeSession()
    monkeypatch.setattr("backend.workflow_executor.page_session_mgr.create", lambda: session)

    # loop: needs upstream select_list context
    request = TestSubflowRequest.model_validate({
        "graph": graph([
            node("open", "open_page", {"url": "http://example.com"}),
            node("list", "select_list", {"item_selector": ".item"}),
            node("lp", "loop", {"max_items": 5}),
            node("en", "end", {}),
        ], [
            {"id": "e1", "source": "open", "target": "list"},
            {"id": "e2", "source": "list", "target": "lp"},
            {"id": "e3", "source": "lp", "target": "en"},
        ]),
        "boundary": {"max_items": 10, "max_steps": 10},
    })

    response = await WorkflowExecutor().test_subflow(request)

    # loop sets context (item_count=0 since no real page), end stops
    node_ids = [result.node_id for result in response.node_results]
    assert "lp" in node_ids
    assert "en" in node_ids
    assert response.node_results[-1].node_id == "en"
    assert response.node_results[-1].result["status"] == "ended"


@pytest.mark.anyio
async def test_extract_field_requires_select_list_context(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr("backend.workflow_executor.page_session_mgr.create", lambda: session)

    request = TestSubflowRequest.model_validate({
        "graph": graph([node("open", "open_page", {"url": "http://example.com"}), node("extract", "extract_field", {"fields": [{"name": "title", "selector": "h2", "type": "text"}]})], [{"id": "e", "source": "open", "target": "extract"}]),
        "boundary": {"start_node_id": "extract", "max_steps": 1},
    })

    response = await WorkflowExecutor().test_subflow(request)

    assert response.success is False
    assert "item_selector not found in context" in response.node_results[0].error


@pytest.mark.anyio
async def test_paginate_reports_absent_selector_without_crawling(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr("backend.workflow_executor.page_session_mgr.create", lambda: session)

    request = TestSubflowRequest.model_validate({
        "graph": graph([node("open", "open_page", {"url": "http://example.com"}), node("page", "paginate", {"pagination_selector": "a.next"})], [{"id": "e", "source": "open", "target": "page"}]),
        "boundary": {"start_node_id": "page", "max_steps": 1},
    })

    response = await WorkflowExecutor().test_subflow(request)

    assert response.success is True
    assert response.node_results[0].result["found"] is False
    assert session.navigated == []


@pytest.mark.anyio
async def test_test_node_runs_prerequisites_in_entry_order(monkeypatch):
    session = FakeSession()
    item = FakeElement(text="Item", children={".name": [FakeElement(text="Item")]})
    session.page._selectors[".item"] = [item]
    monkeypatch.setattr("backend.workflow_executor.page_session_mgr.create", lambda: session)

    request = {
        "graph": graph(
            [
                node("open", "open_page", {"url": "http://example.com/list"}),
                node("list", "select_list", {"item_selector": ".item"}),
                node("extract", "extract_field", {"fields": [{"name": "name", "selector": ".name", "type": "text"}]}),
            ],
            [
                {"id": "e1", "source": "open", "target": "list"},
                {"id": "e2", "source": "list", "target": "extract"},
            ],
        ),
        "node_id": "extract",
        "max_items": 1,
    }

    from backend.workflow_schemas import TestNodeRequest
    response = await WorkflowExecutor().test_node(TestNodeRequest.model_validate(request))

    assert response.success is True
    assert [result.node_id for result in response.logs if result.message.startswith("Executing node")] == ["open", "list", "extract"]
    assert response.result.result["records"] == [{"_index": 0, "name": "Item"}]


@pytest.mark.anyio
async def test_subflow_stops_before_boundary_end_node(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr("backend.workflow_executor.page_session_mgr.create", lambda: session)

    request = TestSubflowRequest.model_validate({
        "graph": graph(
            [node("open", "open_page", {"url": "http://example.com"}), node("loop", "loop")],
            [{"id": "e", "source": "open", "target": "loop"}],
        ),
        "boundary": {"end_node_id": "loop", "max_steps": 2},
    })

    response = await WorkflowExecutor().test_subflow(request)

    assert response.success is True
    assert [result.node_id for result in response.node_results] == ["open"]
    assert all(result.node_id != "loop" for result in response.node_results)


@pytest.mark.anyio
async def test_test_node_unknown_session_reports_expired(monkeypatch):
    from backend.workflow_schemas import TestNodeRequest

    monkeypatch.setattr("backend.workflow_executor.page_session_mgr.get", lambda session_id: None)
    request = TestNodeRequest.model_validate({
        "graph": graph([node("open", "open_page", {"url": "http://example.com"})], []),
        "node_id": "open",
        "session_id": "missing-session",
    })

    response = await WorkflowExecutor().test_node(request)

    assert response.success is False
    assert response.session_expired is True
    assert "Session not found" in response.error


@pytest.mark.anyio
async def test_subflow_unexpected_failure_preserves_partial_outputs(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr("backend.workflow_executor.page_session_mgr.create", lambda: session)

    original_execute_node = WorkflowExecutor._execute_node_sync

    def fail_after_open(self, workflow_node, ctx):
        if workflow_node.id == "boom":
            raise RuntimeError("boom after open")
        return original_execute_node(self, workflow_node, ctx)

    monkeypatch.setattr(WorkflowExecutor, "_execute_node_sync", fail_after_open)
    request = TestSubflowRequest.model_validate({
        "graph": graph(
            [
                node("open", "open_page", {"url": "http://example.com"}),
                node("boom", "select_list", {"item_selector": ".item"}),
                node("after", "select_list", {"item_selector": ".item"}),
            ],
            [{"id": "e1", "source": "open", "target": "boom"}, {"id": "e2", "source": "boom", "target": "after"}],
        ),
        "boundary": {"max_steps": 5},
    })

    response = await WorkflowExecutor().test_subflow(request)

    assert response.success is False
    assert response.partial is True
    assert response.node_results[0].node_id == "open"
    assert all(result.node_id != "after" for result in response.node_results)
    assert "boom after open" in response.error
    assert any("boom after open" in log.message for log in response.logs)


@pytest.mark.anyio
async def test_condition_branch_prefers_edge_metadata_over_position(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr("backend.workflow_executor.page_session_mgr.create", lambda: session)

    request = TestSubflowRequest.model_validate({
        "graph": graph(
            [
                node("open", "open_page", {"url": "http://example.com"}),
                node("cond", "condition", {"condition": "not_exists missing", "expression_mode": "simple"}),
                node("end_true", "end", {}),
                node("end_false", "end", {}),
            ],
            [
                {"id": "e1", "source": "open", "target": "cond"},
                # Intentionally put false edge first to validate metadata precedence.
                {"id": "e2", "source": "cond", "target": "end_false", "branch": "false"},
                {"id": "e3", "source": "cond", "target": "end_true", "branch": "true"},
            ],
        ),
        "boundary": {"max_steps": 10},
    })

    response = await WorkflowExecutor().test_subflow(request)

    assert response.success is True
    assert [result.node_id for result in response.node_results] == ["open", "cond", "end_true"]
    assert all(result.node_id != "end_false" for result in response.node_results)

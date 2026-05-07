# Extension Bridge Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy Local CDP bridge with the Chrome Extension JSON-RPC bridge, make `extension` the only local bridge mode, and preserve assist/workflow behavior through stable API contracts.

**Architecture:** Keep cloud execution on the existing local Playwright session manager, and route all local browser bridging through a new `ext:` agent ID contract backed by `backend/api/ext_relay.py`, `ExtPageSession`, and a new `packages/sea-extension` workspace. Adapt assist and workflow code to call session-level capabilities instead of assuming direct Playwright element handles.

**Tech Stack:** FastAPI, asyncio WebSocket relay, Playwright sync API, React 19, TypeScript, Vite, Chrome Extension Manifest V3, pytest, vitest

---

## File Structure Map

### Backend runtime and relay

- Create: `backend/api/ext_relay.py`
- Create: `backend/runtime/ext_session.py`
- Create: `backend/runtime/ext_session_mgr.py`
- Modify: `backend/app.py`
- Modify: `backend/runtime/browser_session.py`

### Backend assist and workflow

- Modify: `backend/assist/services.py`
- Modify: `backend/workflow/executor.py`
- Modify: `backend/workflow/executor_helpers.py`
- Modify: `backend/workflow/handlers.py`

### Frontend runtime selection

- Create: `frontend/src/features/runtime/executionTarget.ts`
- Create: `frontend/src/features/runtime/executionTarget.test.ts`
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/app/components/WorkbenchToolbar.tsx`
- Modify: `frontend/src/features/assist/useAssistWorkbenchActions.ts`
- Modify: `frontend/src/features/workflow/useWorkflowActions.ts`

### Extension workspace

- Create: `packages/sea-extension/manifest.json`
- Create: `packages/sea-extension/package.json`
- Create: `packages/sea-extension/tsconfig.json`
- Create: `packages/sea-extension/vite.config.ts`
- Create: `packages/sea-extension/extract_js.py`
- Create: `packages/sea-extension/src/background/rpc.ts`
- Create: `packages/sea-extension/src/background/tab_queue.ts`
- Create: `packages/sea-extension/src/background/worker.ts`
- Create: `packages/sea-extension/src/scripts/builtins.ts`
- Create: `packages/sea-extension/src/scripts/registry.ts`
- Create: `packages/sea-extension/src/scripts/auto_detect.ts`
- Create: `packages/sea-extension/src/scripts/highlight.ts`
- Create: `packages/sea-extension/src/scripts/html_extract.ts`
- Create: `packages/sea-extension/src/popup/popup.html`
- Create: `packages/sea-extension/src/popup/popup.ts`

### Tests and docs cleanup

- Create: `tests/test_ext_session_mgr.py`
- Modify: `tests/test_assist_services.py`
- Modify: `tests/test_workflow_executor.py`
- Modify: `frontend/src/services/workflowApi.test.ts`
- Delete: `backend/api/relay.py`
- Delete: `packages/local-bridge/`
- Delete: `docs/local-bridge.md`

### Cross-cutting design choices

- Use `agent_id="ext:<agentId>"` as the only extension routing contract
- Keep backend response payload shapes stable
- Move workflow node behavior away from `ctx.session.page` assumptions where extension cannot provide Playwright element handles
- Use small testable helpers for frontend request shaping rather than hiding logic inside hooks

### Task 1: Add Failing Tests For Extension Session Routing

**Files:**
- Create: `tests/test_ext_session_mgr.py`
- Modify: `tests/test_assist_services.py`
- Modify: `tests/test_workflow_executor.py`

- [ ] **Step 1: Write failing backend tests for extension routing and session invalidation**

```python
# tests/test_ext_session_mgr.py
from backend.runtime.ext_session_mgr import ExtSessionManager


class FakeConn:
    def __init__(self, tab_id: int = 41):
        self._loop = object()
        self.tab_sessions = {}
        self._tab_id = tab_id


class FakeFuture:
    def __init__(self, payload):
        self._payload = payload

    def result(self, timeout=None):
        return self._payload


def test_ext_session_manager_creates_tab_backed_session(monkeypatch):
    manager = ExtSessionManager()
    conn = FakeConn()
    monkeypatch.setattr(
        "backend.api.ext_relay.ext_agents",
        {"agent-1": conn},
        raising=False,
    )
    monkeypatch.setattr(
        "backend.runtime.ext_session_mgr.asyncio.run_coroutine_threadsafe",
        lambda coro, loop: FakeFuture({"ok": True, "result": {"tabId": 41}}),
    )

    session = manager.create("agent-1", "https://example.com")

    assert session.id == "ext-41"
    assert manager.get("ext-41") is session
    assert conn.tab_sessions[41] == "ext-41"


def test_ext_session_manager_marks_session_dead_when_tab_closes():
    manager = ExtSessionManager()
    session = type("StubSession", (), {"id": "ext-41", "tab_id": 41, "is_alive": lambda self: True, "touch": lambda self: None, "close": lambda self: setattr(self, "_closed", True)})()
    manager._sessions["ext-41"] = session
    manager._tab_index[41] = "ext-41"

    manager.on_tab_closed(41)

    assert manager._tab_index == {}
```

```python
# tests/test_assist_services.py
def test_ensure_session_uses_extension_manager_for_ext_agent(monkeypatch):
    created = []

    class FakeSession:
        id = "ext-88"

        def is_alive(self):
            return True

        def navigate(self, url: str, timeout: int = 30000):
            created.append((url, timeout))

    class FakeExtManager:
        def create(self, agent_id: str, url: str | None = None):
            created.append(("create", agent_id, url))
            return FakeSession()

    monkeypatch.setattr("backend.assist.services.ext_session_mgr", FakeExtManager())

    session, error = _ensure_session(None, "https://example.com", "ext:agent-9")

    assert error is None
    assert session.id == "ext-88"
    assert created[0] == ("create", "agent-9", "https://example.com")
```

```python
# tests/test_workflow_executor.py
@pytest.mark.anyio
async def test_test_node_uses_extension_session_for_ext_agent(monkeypatch):
    session = FakeSession()
    captured = []
    monkeypatch.setattr(
        "backend.workflow.executor_helpers.ext_session_mgr.create",
        lambda agent_id: captured.append(agent_id) or session,
    )

    request = TestNodeRequest.model_validate({
        "graph": graph([node("open", "open_page", {"url": "http://example.com"})], []),
        "node_id": "open",
        "agent_id": "ext:desktop-a",
    })

    response = await WorkflowExecutor().test_node(request)

    assert response.success is True
    assert captured == ["desktop-a"]
```

- [ ] **Step 2: Run the targeted tests and verify they fail for missing extension implementation**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ext_session_mgr.py tests/test_assist_services.py tests/test_workflow_executor.py -k "ext or extension" -v`

Expected: FAIL with import errors for `backend.runtime.ext_session_mgr` or failing assertions because `_ensure_session()` and `get_or_create_session()` do not yet route `ext:` agent IDs.

- [ ] **Step 3: Add minimal test scaffolds if import ordering blocks collection**

```python
# If test collection fails before runtime code exists, gate imports inside tests:
def load_manager():
    from backend.runtime.ext_session_mgr import ExtSessionManager
    return ExtSessionManager
```

```python
# Replace direct top-level imports with:
def test_ext_session_manager_creates_tab_backed_session(monkeypatch):
    ExtSessionManager = load_manager()
    manager = ExtSessionManager()
```

- [ ] **Step 4: Re-run the tests to confirm they still fail on behavior, not syntax**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ext_session_mgr.py tests/test_assist_services.py tests/test_workflow_executor.py -k "ext or extension" -v`

Expected: FAIL on behavior assertions such as `agent_id` routing, because implementation is still missing.

- [ ] **Step 5: Commit the red tests**

```bash
git add tests/test_ext_session_mgr.py tests/test_assist_services.py tests/test_workflow_executor.py
git commit -m "test: cover extension session routing"
```

### Task 2: Implement Backend Extension Relay And Session Manager

**Files:**
- Create: `backend/api/ext_relay.py`
- Create: `backend/runtime/ext_session.py`
- Create: `backend/runtime/ext_session_mgr.py`
- Modify: `backend/app.py`
- Modify: `backend/runtime/browser_session.py`
- Delete: `backend/api/relay.py`

- [ ] **Step 1: Implement the new WebSocket JSON-RPC relay**

```python
# backend/api/ext_relay.py
from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/api/ext-relay", tags=["ExtRelay"])
logger = logging.getLogger(__name__)
ext_agents: dict[str, "ExtAgentConn"] = {}


class ExtAgentConn:
    def __init__(self, ws: WebSocket):
        self.ws = ws
        self._loop = asyncio.get_event_loop()
        self._pending: dict[str, asyncio.Future] = {}
        self.tab_sessions: dict[int, str] = {}

    async def send(self, method: str, params: dict, tab_id: int | None = None, timeout: float = 30.0) -> dict:
        req_id = str(uuid.uuid4())
        message = {"id": req_id, "method": method, "params": params}
        if tab_id is not None:
            message["tabId"] = tab_id
        future = self._loop.create_future()
        self._pending[req_id] = future
        await self.ws.send_text(json.dumps(message, ensure_ascii=False))
        try:
            response = await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
        finally:
            self._pending.pop(req_id, None)
        if not response.get("ok"):
            raise RuntimeError(response.get("error", "Extension error"))
        return response

    def _resolve(self, message: dict) -> None:
        future = self._pending.get(message.get("id", ""))
        if future and not future.done():
            future.set_result(message)

    async def recv_loop(self) -> None:
        async for raw in self.ws.iter_text():
            try:
                message = json.loads(raw)
            except Exception:
                continue
            if "id" in message:
                self._resolve(message)
            elif message.get("type") == "event":
                await _handle_ext_event(message)
```

```python
@router.websocket("/agent/{agent_id}")
async def ext_agent_ws(ws: WebSocket, agent_id: str):
    await ws.accept()
    conn = ExtAgentConn(ws)
    ext_agents[agent_id] = conn
    try:
        await conn.recv_loop()
    except WebSocketDisconnect:
        pass
    finally:
        if ext_agents.get(agent_id) is conn:
            ext_agents.pop(agent_id, None)
```

- [ ] **Step 2: Implement `ExtPageSession` and `ExtSessionManager`**

```python
# backend/runtime/ext_session.py
from __future__ import annotations

import asyncio
import time
from concurrent.futures import Future as CFFuture


class ExtPageSession:
    def __init__(self, conn, tab_id: int):
        self.id = f"ext-{tab_id}"
        self._conn = conn
        self.tab_id = tab_id
        self.url = "about:blank"
        self.created_at = time.time()
        self.last_used = time.time()
        self._closed = False

    def touch(self):
        self.last_used = time.time()

    def is_alive(self) -> bool:
        return not self._closed

    def close(self):
        self._closed = True

    def _sync(self, method: str, params: dict, *, timeout: float = 30.0) -> dict:
        cf: CFFuture = asyncio.run_coroutine_threadsafe(
            self._conn.send(method, params, self.tab_id, timeout),
            self._conn._loop,
        )
        result = cf.result(timeout=timeout + 2)
        self.touch()
        return result.get("result", {})

    def navigate(self, url: str, timeout: int = 30000):
        self.url = url
        self._sync("navigate", {"url": url}, timeout=timeout / 1000)

    def auto_detect(self) -> dict:
        return self._sync("exec_script", {"fn": "sea_auto_detect", "args": []})

    def test_selector(self, selector: str, max_samples: int = 5) -> dict:
        return self._sync("exec_script", {"fn": "sea_query_all", "args": [selector, max_samples]})

    def extract_fields(self, item_selector: str, fields: list[dict]) -> list[dict]:
        result = self._sync("exec_script", {"fn": "sea_extract_fields", "args": [item_selector, fields]})
        return result.get("records", [])
```

```python
# backend/runtime/ext_session_mgr.py
from __future__ import annotations

import asyncio
import logging

from backend.runtime.ext_session import ExtPageSession

logger = logging.getLogger(__name__)


class ExtSessionManager:
    def __init__(self):
        self._sessions: dict[str, ExtPageSession] = {}
        self._tab_index: dict[int, str] = {}

    def create(self, agent_id: str, url: str | None = None) -> ExtPageSession:
        from backend.api.ext_relay import ext_agents

        conn = ext_agents.get(agent_id)
        if not conn:
            raise RuntimeError(
                f"Extension agent '{agent_id}' not connected. Please open the extension popup and connect first."
            )
        future = asyncio.run_coroutine_threadsafe(
            conn.send("new_tab", {"url": url or "about:blank"}),
            conn._loop,
        )
        response = future.result(timeout=15)
        tab_id = int(response.get("result", {}).get("tabId"))
        session = ExtPageSession(conn, tab_id)
        self._sessions[session.id] = session
        self._tab_index[tab_id] = session.id
        conn.tab_sessions[tab_id] = session.id
        return session
```

- [ ] **Step 3: Wire the new relay into the app and delete the old CDP branch**

```python
# backend/app.py
from backend.api.ext_relay import router as ext_relay_router

app.include_router(workflow_router)
app.include_router(assist_router)
app.include_router(ext_relay_router)
```

```python
# backend/runtime/browser_session.py
def create(self, agent_id: str | None = None) -> PageSession:
    session = PageSession(get_browser())
    with self._lock:
        expired = self._collect_expired_session_ids()
        for sid in expired:
            old_session = self._sessions.pop(sid, None)
            if old_session is not None:
                old_session.close()
        self._sessions[session.id] = session
    return session
```

```python
# Delete the legacy relay file and import:
# - remove `from backend.api.relay import router as relay_router`
# - remove `app.include_router(relay_router)`
# - delete backend/api/relay.py
```

- [ ] **Step 4: Run the backend relay/session tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ext_session_mgr.py tests/test_assist_services.py tests/test_workflow_executor.py -k "ext or extension" -v`

Expected: PASS for manager creation and routing tests added in Task 1.

- [ ] **Step 5: Commit the backend relay/session infrastructure**

```bash
git add backend/api/ext_relay.py backend/runtime/ext_session.py backend/runtime/ext_session_mgr.py backend/app.py backend/runtime/browser_session.py
git rm backend/api/relay.py
git commit -m "feat: add extension relay runtime"
```

### Task 3: Adapt Assist Services To Extension Sessions

**Files:**
- Modify: `backend/assist/services.py`
- Modify: `tests/test_assist_services.py`

- [ ] **Step 1: Add failing assist tests for extension-backed auto detect, selector testing, and HTML extraction**

```python
def test_auto_detect_uses_extension_session_methods(monkeypatch):
    class FakeSession:
        id = "ext-5"

        def auto_detect(self):
            return {
                "item_selector": ".card",
                "item_count": 4,
                "item_signature": "article|card",
                "pagination_selector": "a.next",
                "pagination_strategy": "click_next",
                "pagination_score": 8,
                "confidence": 0.91,
                "fields": [{"name": "title", "selector": "h2", "type": "text", "confidence": 0.8}],
                "html_fragment": "<article>Sample</article>",
            }

    monkeypatch.setattr("backend.assist.services._ensure_session", lambda session_id, url, agent_id=None: (FakeSession(), None))

    response = auto_detect(AutoDetectRequest(agent_id="ext:agent-a"))

    assert response.success is True
    assert response.session_id == "ext-5"
    assert response.result["item_selector"] == ".card"
```

```python
def test_extract_html_fragment_uses_extension_session_extract_html(monkeypatch):
    class FakeSession:
        id = "ext-5"

        def clear_highlight(self):
            return None

        def extract_html(self, selector: str, max_items: int = 3, include_pagination: bool = False):
            return {
                "html": "<div>ok</div>",
                "truncated": False,
                "original_size": 13,
                "truncated_size": 13,
                "item_count": 1,
            }

    monkeypatch.setattr("backend.assist.services._ensure_session", lambda session_id, url, agent_id=None: (FakeSession(), None))

    response = extract_html_fragment(AssistHtmlExtractRequest(item_selector=".item", agent_id="ext:agent-a"))

    assert response.success is True
    assert response.html_fragment == "<div>ok</div>"
```

- [ ] **Step 2: Run the assist tests to confirm failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_assist_services.py -k "extension or ext" -v`

Expected: FAIL because `auto_detect()` and `extract_html_fragment()` still assume `session.page`.

- [ ] **Step 3: Implement session-aware assist branching**

```python
# backend/assist/services.py
from backend.runtime.ext_session import ExtPageSession
from backend.runtime.ext_session_mgr import ext_session_mgr


def _ensure_session(session_id: str | None, url: str | None, agent_id: str | None = None):
    if agent_id and agent_id.startswith("ext:") and not session_id:
        try:
            session = ext_session_mgr.create(agent_id[4:], url)
        except RuntimeError as error:
            return None, str(error)
        return session, None
```

```python
def auto_detect(request: AutoDetectRequest) -> AutoDetectResponse:
    session, error = _ensure_session(request.session_id, request.url, getattr(request, "agent_id", None))
    if error:
        return AutoDetectResponse(success=False, error=error)

    if isinstance(session, ExtPageSession):
        session.clear_highlight()
        raw = session.auto_detect()
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
```

```python
def run_selector_test(request: AssistSelectorTestRequest) -> AssistSelectorTestResponse:
    session, error = _ensure_session(request.session_id, request.url, getattr(request, "agent_id", None))
    if error:
        return AssistSelectorTestResponse(success=False, error=error)

    if isinstance(session, ExtPageSession):
        session.clear_highlight()
        result = session.test_selector(request.selector, max_samples=request.max_samples)
        highlighted = 0
        if result.get("count", 0) > 0:
            highlighted = session.highlight_selector(request.selector, request.clear_after_ms)
        return AssistSelectorTestResponse(
            success=True,
            session_id=session.id,
            result={
                "match_count": result.get("count", 0),
                "highlighted_count": highlighted,
                "clear_after_ms": request.clear_after_ms,
                "sample_items": result.get("elements", []),
            },
        )
```

```python
def extract_html_fragment(request: AssistHtmlExtractRequest) -> AssistHtmlExtractResponse:
    session, error = _ensure_session(request.session_id, request.url, getattr(request, "agent_id", None))
    if error:
        return AssistHtmlExtractResponse(success=False, error=error)

    if isinstance(session, ExtPageSession):
        session.clear_highlight()
        result = session.extract_html(
            request.item_selector,
            max_items=request.max_items,
            include_pagination=request.include_pagination,
        )
        return AssistHtmlExtractResponse(
            success=True,
            session_id=session.id,
            html_fragment=result.get("html", ""),
            metadata={
                "truncated": result.get("truncated", False),
                "original_size": result.get("original_size", 0),
                "truncated_size": result.get("truncated_size", 0),
                "item_count": result.get("item_count", 0),
            },
        )
```

- [ ] **Step 4: Run the assist service tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_assist_services.py -v`

Expected: PASS, including both existing Playwright-backed cases and the new extension-specific branch coverage.

- [ ] **Step 5: Commit the assist integration**

```bash
git add backend/assist/services.py tests/test_assist_services.py
git commit -m "feat: route assist services through extension sessions"
```

### Task 4: Adapt Workflow Session Selection And Node Handlers

**Files:**
- Modify: `backend/workflow/executor_helpers.py`
- Modify: `backend/workflow/handlers.py`
- Modify: `backend/workflow/executor.py`
- Modify: `tests/test_workflow_executor.py`

- [ ] **Step 1: Add failing workflow tests for extension-backed select, extract, and paginate flows**

```python
@pytest.mark.anyio
async def test_subflow_runs_with_extension_session_methods(monkeypatch):
    class FakeExtSession:
        id = "ext-7"
        url = "http://example.com/list"

        def navigate(self, url, timeout=30000):
            self.url = url

        def test_selector(self, selector: str, max_samples: int = 5):
            if selector == ".item":
                return {
                    "count": 2,
                    "elements": [{"text": "One", "html": "<div>One</div>", "children": 1, "has_image": False, "has_link": True}],
                }
            if selector == "a.next":
                return {"count": 1, "elements": [{"text": "Next", "html": "<a class='next'>Next</a>", "children": 0, "has_image": False, "has_link": True}]}
            return {"count": 0, "elements": []}

        def extract_fields(self, item_selector: str, fields: list[dict]):
            return [{"_index": 0, "title": "One"}, {"_index": 1, "title": "Two"}]

        def click_element(self, selector: str):
            return {"clicked": True, "domChanged": True}

    monkeypatch.setattr("backend.workflow.executor_helpers.ext_session_mgr.create", lambda agent_id: FakeExtSession())
```

```python
    request = TestSubflowRequest.model_validate({
        "graph": graph(
            [
                node("open", "open_page", {"url": "http://example.com/list"}),
                node("list", "select_list", {"item_selector": ".item"}),
                node("extract", "extract_field", {"fields": [{"name": "title", "selector": "h2", "type": "text"}]}),
                node("page", "paginate", {"pagination_selector": "a.next", "pagination_strategy": "click_next"}),
            ],
            [
                {"id": "e1", "source": "open", "target": "list"},
                {"id": "e2", "source": "list", "target": "extract"},
                {"id": "e3", "source": "extract", "target": "page"},
            ],
        ),
        "agent_id": "ext:desktop-a",
    })

    response = await WorkflowExecutor().test_subflow(request)

    assert response.success is True
    assert response.node_results[1].result["match_count"] == 2
    assert response.node_results[2].result["records"][0]["title"] == "One"
    assert response.node_results[3].result["advanced"] is True
```

- [ ] **Step 2: Run the workflow executor tests and confirm failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_workflow_executor.py -k "extension or ext" -v`

Expected: FAIL because handlers still require `ctx.session.page` and Playwright element handles.

- [ ] **Step 3: Refactor workflow handlers to use session-level operations**

```python
# backend/workflow/executor_helpers.py
from backend.runtime.ext_session_mgr import ext_session_mgr


def get_or_create_session(session_id: Optional[str], agent_id: Optional[str] = None):
    if agent_id and agent_id.startswith("ext:"):
        return ext_session_mgr.create(agent_id[4:])
    if session_id:
        session = page_session_mgr.get(session_id)
        if session and session.is_alive():
            return session
        if session:
            page_session_mgr.close(session_id)
        return None
    return page_session_mgr.create()
```

```python
# backend/workflow/handlers.py
def _is_extension_session(session) -> bool:
    return hasattr(session, "test_selector") and hasattr(session, "extract_fields")


def _selector_result(self, session, selector: str, max_samples: int):
    if _is_extension_session(session):
        payload = session.test_selector(selector, max_samples=max_samples)
        return {
            "match_count": payload.get("count", 0),
            "sample_items": payload.get("elements", []),
        }
    test_result = self.selector_tester.test_selector(session.page, selector, max_samples=max_samples)
    return {
        "match_count": test_result.match_count,
        "sample_items": test_result.sample_items,
    }
```

```python
def handle_select_list(self, node, ctx, result):
    selector = node.data.item_selector
    payload = self._selector_result(ctx.session, selector, ctx.selector_sample_limit)
    result.result = {
        "match_count": payload["match_count"],
        "samples": payload["sample_items"],
    }
    ctx.state["item_selector"] = selector
    ctx.state["item_count"] = payload["match_count"]
    ctx.add_log(LogLevel.INFO, f"Found {payload['match_count']} items", node_id=node.id)
```

```python
def handle_extract_field(self, node, ctx, result):
    fields = node.data.fields
    item_selector = ctx.state.get("item_selector")
    if _is_extension_session(ctx.session):
        records = ctx.session.extract_fields(item_selector, fields)
    else:
        records = self.selector_tester.extract_fields_from_items(ctx.session.page, item_selector, fields)
```

```python
def handle_paginate(self, node, ctx, result):
    selector = node.data.pagination_selector
    strategy = (node.data.pagination_strategy or "click_next").strip().lower()
    if _is_extension_session(ctx.session):
        found = ctx.session.test_selector(selector, max_samples=1).get("count", 0) > 0
        advanced = False
        if found and not (ctx.state.get("pages_processed") or 1) >= ctx.max_pages:
            if strategy in {"click_next", "load_more"}:
                advanced = bool(ctx.session.click_element(selector).get("domChanged"))
            elif strategy == "infinite_scroll":
                before = ctx.state.get("item_count", 0)
                ctx.session.scroll_to_bottom()
                after = ctx.session.test_selector(ctx.state.get("item_selector", ""), max_samples=1).get("count", before)
                advanced = after >= before
        result.result = {
            "selector": selector,
            "strategy": strategy,
            "found": found,
            "advanced": advanced,
            "page_number": int(ctx.state.get("pages_processed") or 1) + (1 if advanced else 0),
            "max_pages": ctx.max_pages,
            "message": "Advanced via extension bridge" if advanced else "Pagination checked via extension bridge",
        }
        return
```

```python
# backend/workflow/executor.py
from typing import Any

@dataclass
class ExecutionContext:
    session: Any
```

- [ ] **Step 4: Run the workflow executor tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_workflow_executor.py -v`

Expected: PASS for existing Playwright smoke tests and new extension-session workflow tests.

- [ ] **Step 5: Commit the workflow runtime changes**

```bash
git add backend/workflow/executor_helpers.py backend/workflow/handlers.py backend/workflow/executor.py tests/test_workflow_executor.py
git commit -m "feat: make workflow handlers extension-session aware"
```

### Task 5: Create The Chrome Extension Workspace

**Files:**
- Create: `packages/sea-extension/manifest.json`
- Create: `packages/sea-extension/package.json`
- Create: `packages/sea-extension/tsconfig.json`
- Create: `packages/sea-extension/vite.config.ts`
- Create: `packages/sea-extension/extract_js.py`
- Create: `packages/sea-extension/src/background/rpc.ts`
- Create: `packages/sea-extension/src/background/tab_queue.ts`
- Create: `packages/sea-extension/src/background/worker.ts`
- Create: `packages/sea-extension/src/scripts/builtins.ts`
- Create: `packages/sea-extension/src/scripts/registry.ts`
- Create: `packages/sea-extension/src/scripts/auto_detect.ts`
- Create: `packages/sea-extension/src/scripts/highlight.ts`
- Create: `packages/sea-extension/src/scripts/html_extract.ts`
- Create: `packages/sea-extension/src/popup/popup.html`
- Create: `packages/sea-extension/src/popup/popup.ts`

- [ ] **Step 1: Scaffold the package metadata and build config**

```json
// packages/sea-extension/package.json
{
  "name": "sea-extension",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "extract-js": "python extract_js.py",
    "build": "vite build"
  },
  "devDependencies": {
    "typescript": "^6.0.2",
    "vite": "^8.0.9"
  }
}
```

```json
// packages/sea-extension/manifest.json
{
  "manifest_version": 3,
  "name": "Sea Data Workbench Bridge",
  "version": "1.0.0",
  "description": "Local browser bridge for Sea Data Workbench",
  "permissions": ["tabs", "scripting", "storage", "activeTab"],
  "host_permissions": ["<all_urls>"],
  "background": {
    "service_worker": "dist/worker.js",
    "type": "module"
  },
  "action": {
    "default_popup": "dist/popup/popup.html"
  }
}
```

```ts
// packages/sea-extension/vite.config.ts
import { defineConfig } from "vite"
import { resolve } from "node:path"

export default defineConfig({
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        worker: resolve(__dirname, "src/background/worker.ts"),
        popup: resolve(__dirname, "src/popup/popup.html"),
      },
      output: {
        entryFileNames: "[name].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
    },
  },
})
```

- [ ] **Step 2: Implement the RPC client, tab queue, and worker dispatcher**

```ts
// packages/sea-extension/src/background/rpc.ts
export class RpcClient {
  private ws: WebSocket | null = null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private onMessage?: (msg: RpcMsg) => Promise<RpcResp>

  constructor(private serverUrl: string, private agentId: string) {}

  setHandler(fn: (msg: RpcMsg) => Promise<RpcResp>) {
    this.onMessage = fn
  }

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return
    const url = `${this.serverUrl}/api/ext-relay/agent/${this.agentId}`
    this.ws = new WebSocket(url)
    this.ws.onmessage = async (event) => {
      const msg = JSON.parse(event.data) as RpcMsg
      if (!this.onMessage) return
      const response = await this.onMessage(msg)
      this.ws?.send(JSON.stringify(response))
    }
    this.ws.onclose = () => {
      this.reconnectTimer = setTimeout(() => this.connect(), 3000)
    }
  }
}
```

```ts
// packages/sea-extension/src/background/tab_queue.ts
export class TabQueue {
  private queues = new Map<number, Promise<void>>()

  async enqueue<T>(tabId: number, fn: () => Promise<T>): Promise<T> {
    let release!: () => void
    const token = new Promise<void>((resolve) => {
      release = resolve
    })
    const prev = this.queues.get(tabId) ?? Promise.resolve()
    this.queues.set(tabId, prev.then(() => token))
    await prev
    try {
      return await fn()
    } finally {
      release()
      if (this.queues.get(tabId) === token) {
        this.queues.delete(tabId)
      }
    }
  }
}
```

```ts
// packages/sea-extension/src/background/worker.ts
import { RpcClient } from "./rpc"
import { TabQueue } from "./tab_queue"
import { SCRIPT_REGISTRY } from "../scripts/registry"

const tabQueue = new TabQueue()
let rpc: RpcClient | null = null

async function dispatch(msg: RpcMsg): Promise<RpcResp> {
  const { id, method, params, tabId } = msg
  try {
    if (method === "new_tab") {
      const tab = await chrome.tabs.create({ url: params.url || "about:blank" })
      return { id, ok: true, result: { tabId: tab.id } }
    }
    if (method === "navigate") {
      await chrome.tabs.update(tabId!, { url: params.url })
      return { id, ok: true, tabId, result: { url: params.url } }
    }
    if (method === "exec_script") {
      const fn = SCRIPT_REGISTRY[params.fn]
      const result = await tabQueue.enqueue(tabId!, async () => {
        const response = await chrome.scripting.executeScript({
          target: { tabId: tabId! },
          func: fn,
          args: params.args ?? [],
        })
        return response[0]?.result ?? {}
      })
      return { id, ok: true, tabId, result }
    }
    return { id, ok: false, tabId, error: `Unknown method: ${method}` }
  } catch (error) {
    return { id, ok: false, tabId, error: error instanceof Error ? error.message : "Extension error" }
  }
}
```

- [ ] **Step 3: Implement popup configuration and script registry**

```ts
// packages/sea-extension/src/scripts/builtins.ts
export function sea_query_all(selector: string, maxSamples = 20) {
  try {
    const elements = [...document.querySelectorAll(selector)]
    return {
      count: elements.length,
      elements: elements.slice(0, maxSamples).map((el) => ({
        text: (el.textContent || "").trim().slice(0, 200),
        html: el.outerHTML.slice(0, 600),
        children: el.querySelectorAll("*").length,
        has_image: el.querySelectorAll("img").length > 0,
        has_link: el.querySelectorAll("a[href]").length > 0,
      })),
    }
  } catch (error) {
    return { error: error instanceof Error ? error.message : "query failed", count: 0, elements: [] }
  }
}
```

```ts
// packages/sea-extension/src/scripts/registry.ts
import { sea_query_all, sea_extract_fields, sea_click_and_observe, sea_scroll_bottom, __eval__ } from "./builtins"
import { sea_auto_detect } from "./auto_detect"
import { sea_highlight, sea_clear_highlight } from "./highlight"
import { sea_extract_html, sea_extract_html_with_pagination } from "./html_extract"

export const SCRIPT_REGISTRY = {
  sea_query_all,
  sea_extract_fields,
  sea_click_and_observe,
  sea_scroll_bottom,
  sea_auto_detect,
  sea_highlight,
  sea_clear_highlight,
  sea_extract_html,
  sea_extract_html_with_pagination,
  __eval__,
} as const
```

```ts
// packages/sea-extension/src/popup/popup.ts
const connectBtn = document.getElementById("connect") as HTMLButtonElement
const disconnectBtn = document.getElementById("disconnect") as HTMLButtonElement
const serverUrlInput = document.getElementById("serverUrl") as HTMLInputElement
const agentIdInput = document.getElementById("agentId") as HTMLInputElement

connectBtn.addEventListener("click", () => {
  chrome.runtime.sendMessage({
    type: "CONNECT",
    serverUrl: serverUrlInput.value.trim(),
    agentId: agentIdInput.value.trim(),
  })
})

disconnectBtn.addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "DISCONNECT" })
})
```

- [ ] **Step 4: Build the extension assets**

Run:

```bash
cd packages/sea-extension
python extract_js.py
npm install
npm run build
```

Expected: `dist/worker.js` and `dist/popup/popup.html` are generated without TypeScript or Vite errors.

- [ ] **Step 5: Commit the new extension package**

```bash
git add packages/sea-extension
git commit -m "feat: add chrome extension bridge package"
```

### Task 6: Update Frontend Execution Mode And Request Shaping

**Files:**
- Create: `frontend/src/features/runtime/executionTarget.ts`
- Create: `frontend/src/features/runtime/executionTarget.test.ts`
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/app/components/WorkbenchToolbar.tsx`
- Modify: `frontend/src/features/assist/useAssistWorkbenchActions.ts`
- Modify: `frontend/src/features/workflow/useWorkflowActions.ts`
- Modify: `frontend/src/services/workflowApi.test.ts`

- [ ] **Step 1: Write failing frontend tests for `extension` request shaping**

```ts
// frontend/src/features/runtime/executionTarget.test.ts
import { describe, expect, it } from "vitest"
import { buildRuntimeAgentId } from "./executionTarget"

describe("buildRuntimeAgentId", () => {
  it("omits agent id in cloud mode", () => {
    expect(buildRuntimeAgentId("cloud", "desktop-a")).toBeUndefined()
  })

  it("prefixes ext: in extension mode", () => {
    expect(buildRuntimeAgentId("extension", "desktop-a")).toBe("ext:desktop-a")
  })

  it("trims whitespace before prefixing", () => {
    expect(buildRuntimeAgentId("extension", "  desktop-a  ")).toBe("ext:desktop-a")
  })
})
```

```ts
// frontend/src/services/workflowApi.test.ts
it("postWorkflowAction preserves ext-prefixed agent ids", async () => {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ success: true, data: { ok: true }, warnings: [], meta: {} }),
  } as Response)

  await postWorkflowAction("/api/workflows/test-node", {
    graph: { nodes: [], edges: [] },
    node_id: "node-1",
    agent_id: "ext:desktop-a",
  })

  expect(globalThis.fetch).toHaveBeenCalledWith(
    "/api/workflows/test-node",
    expect.objectContaining({
      body: JSON.stringify({
        graph: { nodes: [], edges: [] },
        node_id: "node-1",
        agent_id: "ext:desktop-a",
      }),
    }),
  )
})
```

- [ ] **Step 2: Run the frontend tests to confirm failure**

Run: `cd frontend && npm run test -- src/features/runtime/executionTarget.test.ts src/services/workflowApi.test.ts`

Expected: FAIL because `executionTarget.ts` does not exist and the UI still uses `'local'`.

- [ ] **Step 3: Implement a shared execution-target helper and update the UI**

```ts
// frontend/src/features/runtime/executionTarget.ts
export type ExecutionMode = "cloud" | "extension"

export function buildRuntimeAgentId(mode: ExecutionMode, agentId: string): string | undefined {
  const trimmed = agentId.trim()
  if (mode !== "extension" || !trimmed) return undefined
  return `ext:${trimmed}`
}
```

```tsx
// frontend/src/app/components/WorkbenchToolbar.tsx
executionMode: "cloud" | "extension"
onExecutionModeChange: (mode: "cloud" | "extension") => void

options={[
  { label: "Cloud", value: "cloud" },
  { label: "Extension", value: "extension" },
]}

{executionMode === "extension" && (
  <Input size="small" placeholder="Agent ID" value={agentId} onChange={(e) => onAgentIdChange(e.target.value)} />
)}
```

```tsx
// frontend/src/app/App.tsx
const [executionMode, setExecutionMode] = useState<"cloud" | "extension">(
  () => (localStorage.getItem("executionMode") as "cloud" | "extension") || "cloud",
)
```

```ts
// frontend/src/features/assist/useAssistWorkbenchActions.ts
import { buildRuntimeAgentId, type ExecutionMode } from "../runtime/executionTarget"

function withAssistSession<T extends Record<string, unknown>>(payload: T): T & { session_id?: string; agent_id?: string } {
  const result: Record<string, unknown> = { ...payload }
  if (assistSessionId) result.session_id = assistSessionId
  const runtimeAgentId = buildRuntimeAgentId(executionMode, agentId)
  if (runtimeAgentId) result.agent_id = runtimeAgentId
  return result as T & { session_id?: string; agent_id?: string }
}
```

```ts
// frontend/src/features/workflow/useWorkflowActions.ts
const runtimeAgentId = buildRuntimeAgentId(executionMode, agentId)
const requestBody =
  (action === "test-node" || action === "test-subflow") && runtimeAgentId
    ? { ...basePayload, agent_id: runtimeAgentId }
    : basePayload
```

- [ ] **Step 4: Run the frontend tests and build**

Run:

```bash
cd frontend
npm run test -- src/features/runtime/executionTarget.test.ts src/services/workflowApi.test.ts
npm run build
```

Expected: PASS for both tests and a clean production build.

- [ ] **Step 5: Commit the frontend runtime switch**

```bash
git add frontend/src/features/runtime/executionTarget.ts frontend/src/features/runtime/executionTarget.test.ts frontend/src/app/App.tsx frontend/src/app/components/WorkbenchToolbar.tsx frontend/src/features/assist/useAssistWorkbenchActions.ts frontend/src/features/workflow/useWorkflowActions.ts frontend/src/services/workflowApi.test.ts
git commit -m "feat: switch local runtime mode to extension"
```

### Task 7: Remove Legacy Bridge Artifacts And Run Full Verification

**Files:**
- Delete: `packages/local-bridge/`
- Delete: `docs/local-bridge.md`
- Modify: `docs/extension-bridge.md` if any setup paths changed during implementation

- [ ] **Step 1: Remove the old bridge package and stale docs**

```bash
git rm -r packages/local-bridge
git rm docs/local-bridge.md
```

```text
If `docs/extension-bridge.md` or `docs/extension-bridge-scripts.md` diverged from the implemented file paths, update them in the same change so the repo has one truthful setup path.
```

- [ ] **Step 2: Run the full backend and frontend verification suite**

Run:

```bash
.venv\Scripts\python.exe -m pytest tests/test_ext_session_mgr.py tests/test_assist_services.py tests/test_workflow_executor.py tests/test_workflow_api.py -v
cd frontend && npm run test && npm run build
```

Expected: PASS across Python and frontend test suites.

- [ ] **Step 3: Run extension package build verification**

Run:

```bash
cd packages/sea-extension
python extract_js.py
npm install
npm run build
```

Expected: PASS, with generated extension assets ready to load into Chrome.

- [ ] **Step 4: Perform manual end-to-end checks**

```text
1. Start backend: `python server.py`
2. Load `packages/sea-extension` as an unpacked Chrome extension
3. Connect popup to `ws://127.0.0.1:<backend_port>` with agent ID `desktop-a`
4. In the frontend choose `Extension`, enter `desktop-a`, and run:
   - `test-node` on `open_page`
   - `test-node` on `select_list`
   - assist `测试选择器`
   - assist `自动检测`
   - assist `分页分析`
5. Close the created browser tab and verify the next action returns session-expired style feedback
```

- [ ] **Step 5: Commit the removal and verification changes**

```bash
git add docs/extension-bridge.md docs/extension-bridge-scripts.md
git commit -m "chore: remove local cdp bridge artifacts"
```

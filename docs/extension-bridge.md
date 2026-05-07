# Chrome Extension Bridge 技术实施指南

> 替代 `packages/local-bridge` 的完整方案。面向后续 Agent 编码使用，可直接按章节执行。

---

## 一、背景与核心决策

### 废弃 CDP 透传，改用 JSON-RPC

旧方案通过 WebSocket 透传 CDP 二进制流，链路复杂且易出并发 Bug（已有记录）。  
新方案：Extension 直接用 Chrome API 操作 Tab，与后端用简单 JSON-RPC 通信。

### 关键发现

`backend/extraction/auto_detector.py` 的核心是 `JS_AUTO_DETECT`（纯 JS 字符串）。  
`html_extractor.py`、`selector_tester.py` 的浏览器操作全部通过 `page.evaluate(js)` 执行。  
**这些 JS 可直接被 Extension 的 `executeScript` 调用，零重写。**

---

## 二、删除文件

```
packages/local-bridge/          ← 整个目录删除
backend/api/relay.py            ← 删除（CDP 透传）
```

`backend/app.py` 中移除 `relay_router` 的 import 和 `include_router`。  
`backend/runtime/browser_session.py` 中删除 `connect_over_cdp` 分支（`create` 方法中 `if agent_id:` 块）。

---

## 三、新增后端文件

### 3.1 `backend/api/ext_relay.py`

```python
"""Chrome Extension WebSocket 中继 — JSON-RPC 协议。"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio, json, logging, uuid

router = APIRouter(prefix="/api/ext-relay", tags=["ExtRelay"])
logger = logging.getLogger(__name__)

# 全局注册表：agent_id → ExtAgentConn
ext_agents: dict[str, "ExtAgentConn"] = {}


class ExtAgentConn:
    def __init__(self, ws: WebSocket):
        self.ws = ws
        self._loop = asyncio.get_event_loop()
        self._pending: dict[str, asyncio.Future] = {}
        # tab_id → session_id 映射，用于 tab_closed 事件处理
        self.tab_sessions: dict[int, str] = {}

    async def send(self, method: str, params: dict,
                   tab_id: int | None = None, timeout: float = 30.0) -> dict:
        req_id = str(uuid.uuid4())
        msg: dict = {"id": req_id, "method": method, "params": params}
        if tab_id is not None:
            msg["tabId"] = tab_id
        fut = self._loop.create_future()
        self._pending[req_id] = fut
        await self.ws.send_text(json.dumps(msg, ensure_ascii=False))
        try:
            resp = await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Extension did not respond in {timeout}s (method={method})")
        finally:
            self._pending.pop(req_id, None)
        if not resp.get("ok"):
            raise RuntimeError(resp.get("error", "Extension error"))
        return resp

    # 由 recv_loop 调用，不对外暴露
    def _resolve(self, msg: dict):
        fut = self._pending.get(msg.get("id", ""))
        if fut and not fut.done():
            fut.set_result(msg)

    async def recv_loop(self):
        async for raw in self.ws.iter_text():
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if "id" in msg:
                self._resolve(msg)
            elif msg.get("type") == "event":
                await _handle_ext_event(msg)


async def _handle_ext_event(msg: dict):
    event = msg.get("event")
    tab_id = msg.get("tabId")
    if event == "tab_closed" and tab_id:
        logger.info(f"[ExtRelay] Tab closed: {tab_id}")
        # 通知 ext_session_mgr 标记 session 为 dead
        from backend.runtime.ext_session_mgr import ext_session_mgr
        ext_session_mgr.on_tab_closed(tab_id)
    elif event == "tab_navigated":
        logger.debug(f"[ExtRelay] Tab navigated: {tab_id} → {msg.get('url')}")


@router.websocket("/agent/{agent_id}")
async def ext_agent_ws(ws: WebSocket, agent_id: str):
    await ws.accept()
    conn = ExtAgentConn(ws)
    ext_agents[agent_id] = conn
    logger.info(f"[ExtRelay] Extension connected: {agent_id}")
    try:
        await conn.recv_loop()
    except WebSocketDisconnect:
        pass
    finally:
        if ext_agents.get(agent_id) is conn:
            ext_agents.pop(agent_id, None)
        logger.info(f"[ExtRelay] Extension disconnected: {agent_id}")
```

---

### 3.2 `backend/runtime/ext_session.py`

```python
"""ExtPageSession — 与 Extension 通信的浏览器会话，提供与 PageSession 兼容的同步接口。"""
from __future__ import annotations
import asyncio, time
from concurrent.futures import Future as CFFuture
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.api.ext_relay import ExtAgentConn


class ExtPageSession:
    """同步接口，内部通过 asyncio.run_coroutine_threadsafe 桥接异步 WS 调用。"""

    def __init__(self, conn: ExtAgentConn, tab_id: int):
        self.id = f"ext-{tab_id}"
        self._conn = conn
        self.tab_id = tab_id
        self.created_at = time.time()
        self.last_used = time.time()
        self._closed = False

    # ── 生命周期 ──────────────────────────────────────────────

    def touch(self):
        self.last_used = time.time()

    def is_alive(self) -> bool:
        return not self._closed

    def close(self):
        self._closed = True

    # ── 内部同步桥接 ──────────────────────────────────────────

    def _sync(self, method: str, params: dict,
              tab_id: int | None = None, timeout: float = 30.0) -> dict:
        """在线程池中同步等待异步命令完成。"""
        loop = self._conn._loop
        cf: CFFuture = asyncio.run_coroutine_threadsafe(
            self._conn.send(method, params, tab_id or self.tab_id, timeout),
            loop,
        )
        result = cf.result(timeout=timeout + 2)
        self.touch()
        return result.get("result", {})

    def _exec(self, fn: str, args: list, timeout: float = 30.0) -> dict:
        return self._sync("exec_script", {"fn": fn, "args": args}, timeout=timeout)

    # ── 对 handlers.py 暴露的接口（与 PageSession 兼容）─────────

    def navigate(self, url: str, timeout: int = 30000) -> None:
        self._sync("navigate", {"url": url}, timeout=timeout / 1000)

    def evaluate(self, js: str) -> object:
        """直接执行 JS 字符串（对应 page.evaluate）。"""
        r = self._exec("__eval__", [js])
        return r.get("value")

    def query_selector_all(self, selector: str) -> list:
        """返回序列化的元素信息列表（非 ElementHandle）。"""
        r = self._exec("sea_query_all", [selector])
        return r.get("elements", [])

    # ── 辅助方法（对应 SelectorTester / HtmlExtractor 用到的） ──

    def highlight_selector(self, selector: str, clear_after_ms: int = 2200) -> int:
        r = self._exec("sea_highlight", [selector, clear_after_ms])
        return r.get("highlighted_count", 0)

    def clear_highlight(self) -> None:
        self._exec("sea_clear_highlight", [])

    def auto_detect(self) -> dict:
        """运行 JS_AUTO_DETECT，返回检测结果 dict。"""
        r = self._exec("sea_auto_detect", [])
        return r

    def extract_html(self, selector: str, max_items: int = 3,
                     include_pagination: bool = False) -> dict:
        fn = "sea_extract_html_with_pagination" if include_pagination else "sea_extract_html"
        r = self._exec(fn, [selector, max_items])
        return r

    def test_selector(self, selector: str, max_samples: int = 5) -> dict:
        r = self._exec("sea_query_all", [selector, max_samples])
        return r

    def extract_fields(self, item_selector: str, fields: list) -> list:
        r = self._exec("sea_extract_fields", [item_selector, fields])
        return r.get("records", [])

    def click_element(self, selector: str) -> dict:
        r = self._exec("sea_click_and_observe", [selector, 5000])
        return r

    def scroll_to_bottom(self) -> None:
        self._exec("sea_scroll_bottom", [])
```

---

### 3.3 `backend/runtime/ext_session_mgr.py`

```python
"""ExtSessionManager — Extension 会话注册表。"""
from __future__ import annotations
import logging
from backend.runtime.ext_session import ExtPageSession

logger = logging.getLogger(__name__)


class ExtSessionManager:
    def __init__(self):
        self._sessions: dict[str, ExtPageSession] = {}
        # tabId → session_id 反向索引
        self._tab_index: dict[int, str] = {}

    def create(self, agent_id: str, url: str | None = None) -> ExtPageSession:
        from backend.api.ext_relay import ext_agents
        import asyncio
        conn = ext_agents.get(agent_id)
        if not conn:
            raise RuntimeError(
                f"Extension agent '{agent_id}' not connected. "
                "Please open the Sea Data Extension and connect first."
            )
        loop = conn._loop
        import concurrent.futures as cf
        future = asyncio.run_coroutine_threadsafe(
            conn.send("new_tab", {"url": url or "about:blank"}), loop
        )
        result = future.result(timeout=15)
        tab_id: int = result.get("result", {}).get("tabId")
        if not tab_id:
            raise RuntimeError("Extension did not return a valid tabId")
        session = ExtPageSession(conn, tab_id)
        self._sessions[session.id] = session
        self._tab_index[tab_id] = session.id
        conn.tab_sessions[tab_id] = session.id
        logger.info(f"[ExtSessionMgr] Created session {session.id} for tab {tab_id}")
        return session

    def get(self, session_id: str) -> ExtPageSession | None:
        s = self._sessions.get(session_id)
        if s and s.is_alive():
            s.touch()
            return s
        return None

    def close(self, session_id: str) -> bool:
        s = self._sessions.pop(session_id, None)
        if s:
            self._tab_index.pop(s.tab_id, None)
            s.close()
            return True
        return False

    def on_tab_closed(self, tab_id: int):
        """由 ext_relay 事件处理器调用。"""
        session_id = self._tab_index.pop(tab_id, None)
        if session_id:
            s = self._sessions.get(session_id)
            if s:
                s.close()
                logger.info(f"[ExtSessionMgr] Session {session_id} marked dead (tab closed)")


ext_session_mgr = ExtSessionManager()
```

---

## 四、修改现有后端文件

### 4.1 `backend/app.py`

```python
# 删除：
from backend.api.relay import router as relay_router
app.include_router(relay_router)

# 新增：
from backend.api.ext_relay import router as ext_relay_router
app.include_router(ext_relay_router)
```

### 4.2 `backend/workflow/executor_helpers.py` — `get_or_create_session`

```python
def get_or_create_session(session_id: str | None, agent_id: str | None = None):
    if agent_id and agent_id.startswith("ext:"):
        real_agent_id = agent_id[4:]
        from backend.runtime.ext_session_mgr import ext_session_mgr
        return ext_session_mgr.create(real_agent_id)

    # 原 Playwright 路径保持不变
    if session_id:
        session = page_session_mgr.get(session_id)
        if session and session.is_alive():
            return session
        if session:
            page_session_mgr.close(session_id)
        return None
    return page_session_mgr.create()
```

### 4.3 `backend/assist/services.py` — `_ensure_session`

```python
def _ensure_session(session_id: str | None, url: str | None,
                    agent_id: str | None = None):
    # Extension 路径
    if agent_id and agent_id.startswith("ext:"):
        real_agent_id = agent_id[4:]
        from backend.runtime.ext_session_mgr import ext_session_mgr
        try:
            session = ext_session_mgr.create(real_agent_id, url)
        except RuntimeError as e:
            return None, str(e)
        return session, None

    # 原 Playwright 路径（保持不变）
    ...
```

### 4.4 `backend/assist/services.py` — 适配 `ExtPageSession` 接口

`auto_detect`、`run_selector_test`、`extract_html_fragment` 三个函数调用 Playwright API 的地方，需要判断 session 类型：

```python
from backend.runtime.ext_session import ExtPageSession

# 在 auto_detect 中：
if isinstance(session, ExtPageSession):
    raw = session.auto_detect()
    # raw 已是 dict，直接用
    result = DetectionResult(
        item_selector=raw.get("item_selector", ""),
        item_count=raw.get("item_count", 0),
        ...
    )
else:
    detector = AutoDetector()
    result = detector.detect(session.page)
```

---

## 五、Extension 完整代码

详见 `docs/extension-bridge-scripts.md`（下一个文件）。

---

## 六、前端改造

### `frontend/src/app/components/WorkbenchToolbar.tsx`

在执行环境 Select 中增加选项：
```tsx
{ value: 'extension', label: '🧩 Extension' }
```

### `frontend/src/app/App.tsx`

`agent_id` 格式规则：
- Cloud: `agent_id = null`
- Extension: `agent_id = "ext:" + agentIdInput`

其余 API 调用无需改动（`agent_id` 字段已存在）。

---

## 七、异常场景处理

| 场景 | 处理位置 | 处理方式 |
|---|---|---|
| Extension 未连接 | `ext_session_mgr.create()` | 抛出友好 RuntimeError，前端展示 |
| Tab 被用户关闭 | `ext_relay._handle_ext_event` | 标记 session dead，下次调用返回 session_expired |
| JS 执行超时 | `ExtPageSession._sync()` | 抛出 TimeoutError，统一错误格式回传 |
| 无效 CSS 选择器 | Extension JS 内 try/catch | 返回 `{"error": "..."}` |
| WS 断线 | Extension worker.ts | 3s 自动重连 |
| HTML 超过 15KB | `sea_extract_html` JS 内截断 | 与原 `HtmlExtractor.MAX_FRAGMENT_SIZE` 一致 |
| CSP 阻断脚本 | N/A | Extension `scripting` 权限免疫 |

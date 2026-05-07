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
        self._loop = asyncio.get_running_loop()
        self._pending: dict[str, asyncio.Future] = {}
        self.tab_sessions: dict[int, str] = {}

    async def send(
        self,
        method: str,
        params: dict,
        tab_id: int | None = None,
        timeout: float = 30.0,
    ) -> dict:
        req_id = str(uuid.uuid4())
        message: dict[str, object] = {"id": req_id, "method": method, "params": params}
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
            raise RuntimeError(str(response.get("error") or "Extension error"))
        return response

    def _resolve(self, message: dict) -> None:
        future = self._pending.get(str(message.get("id") or ""))
        if future is not None and not future.done():
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


async def _handle_ext_event(message: dict) -> None:
    event = str(message.get("event") or "")
    tab_id = message.get("tabId")
    if event == "tab_closed" and isinstance(tab_id, int):
        from backend.runtime.ext_session_mgr import ext_session_mgr

        logger.info("[ExtRelay] Tab closed: %s", tab_id)
        ext_session_mgr.on_tab_closed(tab_id)
    elif event == "tab_navigated" and isinstance(tab_id, int):
        logger.debug("[ExtRelay] Tab navigated: %s -> %s", tab_id, message.get("url"))


@router.websocket("/agent/{agent_id}")
async def ext_agent_ws(ws: WebSocket, agent_id: str):
    await ws.accept()
    conn = ExtAgentConn(ws)
    ext_agents[agent_id] = conn
    logger.info("[ExtRelay] Extension connected: %s", agent_id)
    try:
        await conn.recv_loop()
    except WebSocketDisconnect:
        pass
    finally:
        if ext_agents.get(agent_id) is conn:
            ext_agents.pop(agent_id, None)
        logger.info("[ExtRelay] Extension disconnected: %s", agent_id)

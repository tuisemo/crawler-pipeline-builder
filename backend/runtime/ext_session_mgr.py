from __future__ import annotations

import asyncio
import logging
import threading

from backend.runtime.ext_session import ExtPageSession

logger = logging.getLogger(__name__)


class ExtSessionManager:
    def __init__(self):
        self._sessions: dict[str, ExtPageSession] = {}
        self._tab_index: dict[int, str] = {}
        self._lock = threading.Lock()

    def create(self, agent_id: str, url: str | None = None) -> ExtPageSession:
        from backend.api.ext_relay import ext_agents

        conn = ext_agents.get(agent_id)
        if conn is None:
            raise RuntimeError(
                f"Extension agent '{agent_id}' not connected. Please open the extension popup and connect first."
            )
        future = asyncio.run_coroutine_threadsafe(
            conn.send("new_tab", {"url": url or "about:blank"}),
            conn._loop,
        )
        response = future.result(timeout=15)
        raw_tab_id = response.get("result", {}).get("tabId")
        if not isinstance(raw_tab_id, int):
            raise RuntimeError("Extension did not return a valid tabId")
        session = ExtPageSession(conn, raw_tab_id, url=url)
        with self._lock:
            self._sessions[session.id] = session
            self._tab_index[raw_tab_id] = session.id
            conn.tab_sessions[raw_tab_id] = session.id
        logger.info("[ExtSessionMgr] Created session %s for agent %s", session.id, agent_id)
        return session

    def get(self, session_id: str | None) -> ExtPageSession | None:
        if not session_id:
            return None
        with self._lock:
            session = self._sessions.get(session_id)
        if session and session.is_alive():
            session.touch()
            return session
        return None

    def close(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                self._tab_index.pop(session.tab_id, None)
        if session:
            session.close()
            return True
        return False

    def on_tab_closed(self, tab_id: int):
        with self._lock:
            session_id = self._tab_index.pop(tab_id, None)
            session = self._sessions.get(session_id) if session_id else None
        if session is not None:
            session.close()
            logger.info("[ExtSessionMgr] Session %s marked dead", session.id)


ext_session_mgr = ExtSessionManager()

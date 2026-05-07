class FakeConn:
    def __init__(self, tab_id: int = 41):
        self._loop = object()
        self.tab_sessions: dict[int, str] = {}
        self._tab_id = tab_id

    async def send(self, method: str, params: dict):
        return {"ok": True, "result": {"tabId": self._tab_id}}


class FakeFuture:
    def __init__(self, payload):
        self._payload = payload

    def result(self, timeout=None):
        return self._payload


def load_manager():
    from backend.runtime.ext_session_mgr import ExtSessionManager

    return ExtSessionManager


def test_ext_session_manager_creates_tab_backed_session(monkeypatch):
    ExtSessionManager = load_manager()
    manager = ExtSessionManager()
    conn = FakeConn()
    monkeypatch.setattr(
        "backend.api.ext_relay.ext_agents",
        {"agent-1": conn},
        raising=False,
    )
    monkeypatch.setattr(
        "backend.runtime.ext_session_mgr.asyncio.run_coroutine_threadsafe",
        lambda coro, loop: (coro.close(), FakeFuture({"ok": True, "result": {"tabId": 41}}))[1],
    )

    session = manager.create("agent-1", "https://example.com")

    assert session.id == "ext-41"
    assert manager.get("ext-41") is session
    assert conn.tab_sessions[41] == "ext-41"


def test_ext_session_manager_marks_session_dead_when_tab_closes():
    ExtSessionManager = load_manager()
    manager = ExtSessionManager()

    class StubSession:
        id = "ext-41"
        tab_id = 41

        def __init__(self):
            self.closed = False

        def is_alive(self):
            return not self.closed

        def touch(self):
            return None

        def close(self):
            self.closed = True

    session = StubSession()
    manager._sessions["ext-41"] = session
    manager._tab_index[41] = "ext-41"

    manager.on_tab_closed(41)

    assert manager._tab_index == {}
    assert session.closed is True

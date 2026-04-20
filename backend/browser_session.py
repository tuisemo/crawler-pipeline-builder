import time
import threading
import uuid
from playwright.sync_api import sync_playwright

_playwright = None
_browser = None
_browser_lock = threading.Lock()
_global_context = None
_global_context_lock = threading.Lock()
_shared_context_browser_id = None

def get_browser():
    global _playwright, _browser, _global_context, _shared_context_browser_id
    with _browser_lock:
        if _browser is None or not _browser.is_connected():
            if _browser is not None:
                try:
                    _browser.close()
                except Exception:
                    pass
            if _playwright is None:
                _playwright = sync_playwright().start()
            _browser = _playwright.chromium.launch(
                headless=False,
                args=["--start-maximized", "--no-sandbox", "--disable-dev-shm-usage"],
            )
            # Browser instance changed, so shared context must be recreated.
            _global_context = None
            _shared_context_browser_id = None
        return _browser

def _context_alive(context) -> bool:
    if context is None:
        return False
    try:
        # Accessing pages on a closed context raises, which lets us detect stale refs.
        context.pages
        return True
    except Exception:
        return False

def get_shared_context():
    """Get or create the global shared browser context."""
    global _global_context, _shared_context_browser_id
    with _global_context_lock:
        browser = get_browser()
        browser_id = id(browser)
        if (
            _global_context is None
            or _shared_context_browser_id != browser_id
            or not _context_alive(_global_context)
        ):
            _global_context = browser.new_context(no_viewport=True)
            _shared_context_browser_id = browser_id
        return _global_context

def stop_browser():
    global _playwright, _browser, _global_context, _shared_context_browser_id
    with _global_context_lock:
        if _global_context is not None:
            try:
                _global_context.close()
            except Exception:
                pass
            _global_context = None
            _shared_context_browser_id = None
    with _browser_lock:
        if _browser:
            try:
                _browser.close()
            except Exception:
                pass
            _browser = None
        if _playwright is not None:
            try:
                _playwright.stop()
            except Exception:
                pass
            _playwright = None


class PageSession:
    """Holds a dedicated browser context + page for a user session."""

    def __init__(self, browser, context=None):
        self.id = str(uuid.uuid4())[:8]
        self.browser = browser
        self.context = context or browser.new_context(no_viewport=True)
        self.page = self.context.new_page()
        self.created_at = time.time()
        self.last_used = time.time()
        self._closed = False

    def touch(self):
        self.last_used = time.time()

    def is_alive(self) -> bool:
        if self._closed:
            return False
        try:
            if self.browser is None or not self.browser.is_connected():
                return False
            return not self.page.is_closed()
        except Exception:
            return False

    def close(self):
        self._closed = True
        try:
            self.page.close()
        except Exception:
            pass

    def navigate(self, url: str, timeout: int = 30000):
        """Navigate to URL on the session's page."""
        self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)

    def new_page(self):
        """Create a new page in the existing context (tab in same browser window)."""
        if self._closed:
            raise RuntimeError("Session is closed")
        new_page = self.context.new_page()
        return new_page


class SessionManager:
    """Thread-safe session registry with TTL-based cleanup.

    Each session has its own page but shares the global context,
    so operations open new tabs (not new windows).
    """

    def __init__(self, ttl_seconds: int = 600):
        self._sessions: dict[str, PageSession] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
        self._cleanup_interval = 120
        self._timer = None

    def _schedule_cleanup(self):
        if self._timer is not None:
            return
        def background():
            while True:
                time.sleep(self._cleanup_interval)
                self.cleanup()
        t = threading.Thread(target=background, daemon=True)
        t.start()
        self._timer = t

    def cleanup(self):
        now = time.time()
        with self._lock:
            expired = [sid for sid, s in self._sessions.items()
                       if now - s.last_used > self._ttl or not s.is_alive()]
            for sid in expired:
                self._sessions[sid].close()
                del self._sessions[sid]

    def get(self, session_id: str | None) -> PageSession | None:
        if not session_id:
            return None
        with self._lock:
            s = self._sessions.get(session_id)
            if s:
                s.touch()
            return s

    def create(self) -> PageSession:
        self._schedule_cleanup()
        ctx = get_shared_context()
        session = PageSession(get_browser(), context=ctx)
        with self._lock:
            self._sessions[session.id] = session
        return session

    def close(self, session_id: str) -> bool:
        with self._lock:
            s = self._sessions.pop(session_id, None)
        if s:
            s.close()
            return True
        return False

    def close_all(self):
        with self._lock:
            for s in self._sessions.values():
                s.close()
            self._sessions.clear()

    def get_most_recent(self):
        """Return the most recently used session, or None."""
        with self._lock:
            if not self._sessions:
                return None
            return max(self._sessions.values(), key=lambda s: s.last_used)

page_session_mgr = SessionManager(ttl_seconds=600)

def get_active_session():
    """Get the most recently used session, or create a new one."""
    session = page_session_mgr.get_most_recent()
    if session is None:
        session = page_session_mgr.create()
    return session

def classify_error(e: Exception) -> dict:
    """Classify error into user-friendly categories."""
    msg = str(e)
    if "timeout" in msg.lower() or "Timeout" in msg:
        return {"error": "页面加载超时，请检查网络或目标站点是否可访问", "error_type": "timeout"}
    if "net::ERR" in msg or "Resolve" in msg:
        return {"error": f"无法解析目标地址: {msg}", "error_type": "network"}
    if "selector" in msg.lower() and ("invalid" in msg.lower() or "not found" in msg.lower()):
        return {"error": f"无效的选择器: {msg}", "error_type": "selector"}
    if "session" in msg.lower() and "not found" in msg.lower():
        return {"error": "会话已过期，请重新访问页面", "error_type": "session"}
    return {"error": msg, "error_type": "unknown"}

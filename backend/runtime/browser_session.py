import time
import uuid
import threading
from playwright.sync_api import sync_playwright

from backend.core.settings import get_settings

_playwright = None
_browser = None
_browser_lock = threading.Lock()


def get_browser():
    """Get or create the singleton Playwright Chromium browser instance.
    
    The browser process is shared across all sessions for efficiency,
    but each session gets its own isolated browser context.
    """
    global _playwright, _browser
    with _browser_lock:
        if _browser is None or not _browser.is_connected():
            if _browser is not None:
                try:
                    _browser.close()
                except Exception:
                    pass
            if _playwright is None:
                _playwright = sync_playwright().start()
            settings = get_settings()
            _browser = _playwright.chromium.launch(
                headless=settings.browser_headless,
                args=["--start-maximized", "--no-sandbox", "--disable-dev-shm-usage"],
            )
        return _browser


def stop_browser():
    """Stop the Playwright browser and associated playwright instance."""
    global _playwright, _browser
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
    """Holds an isolated browser context + page for a user session.
    
    Each PageSession has its own browser context, ensuring complete isolation:
    - Cookies are NOT shared between sessions
    - localStorage and sessionStorage are NOT shared between sessions
    - Closing one session does not affect other sessions' pages or contexts
    """

    def __init__(self, browser):
        self.id = str(uuid.uuid4())[:8]
        self.browser = browser
        # Each session creates its own isolated context
        self.context = browser.new_context(no_viewport=True)
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
        """Close the session's page and context.
        
        This properly cleans up both the page and the isolated context,
        ensuring no resource leaks. Safe to call multiple times.
        """
        self._closed = True
        try:
            self.page.close()
        except Exception:
            pass
        try:
            self.context.close()
        except Exception:
            pass

    def navigate(self, url: str, timeout: int = 30000):
        """Navigate to URL on the session's page."""
        self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        try:
            self.page.wait_for_load_state("networkidle", timeout=min(timeout, 10000))
        except Exception:
            pass
        try:
            self.page.wait_for_timeout(800)
        except Exception:
            pass

    def new_page(self):
        """Create a new page in the existing context (tab in same browser window)."""
        if self._closed:
            raise RuntimeError("Session is closed")
        new_page = self.context.new_page()
        return new_page


class SessionManager:
    """Thread-safe session registry with TTL-based cleanup.

    Each session has its own isolated browser context and page.
    Sessions do NOT share contexts, ensuring complete isolation.
    """

    def __init__(self, ttl_seconds: int = 600):
        self._sessions: dict[str, PageSession] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def _collect_expired_session_ids(self, now: float | None = None) -> list[str]:
        current_time = now or time.time()
        return [
            sid
            for sid, session in self._sessions.items()
            if current_time - session.last_used > self._ttl or session._closed
        ]

    def cleanup(self):
        with self._lock:
            expired = self._collect_expired_session_ids()
            sessions = [self._sessions.pop(sid) for sid in expired if sid in self._sessions]
        for session in sessions:
            session.close()

    def get(self, session_id: str | None) -> PageSession | None:
        if not session_id:
            return None
        with self._lock:
            expired = self._collect_expired_session_ids()
            for sid in expired:
                session = self._sessions.pop(sid, None)
                if session is not None:
                    session.close()
            s = self._sessions.get(session_id)
            if s:
                s.touch()
            return s

    def create(self) -> PageSession:
        """Create a new session with its own isolated browser context."""
        # Each session gets its own context from the shared browser process
        session = PageSession(get_browser())
        with self._lock:
            expired = self._collect_expired_session_ids()
            for sid in expired:
                old_session = self._sessions.pop(sid, None)
                if old_session is not None:
                    old_session.close()
            self._sessions[session.id] = session
        return session

    def close(self, session_id: str) -> bool:
        """Close and remove a session by ID. Returns True if session was found."""
        with self._lock:
            s = self._sessions.pop(session_id, None)
        if s:
            s.close()
            return True
        return False

    def close_all(self):
        """Close all sessions and clear the registry."""
        with self._lock:
            for s in self._sessions.values():
                s.close()
            self._sessions.clear()

    def get_most_recent(self):
        """Return the most recently used session, or None."""
        with self._lock:
            expired = self._collect_expired_session_ids()
            for sid in expired:
                session = self._sessions.pop(sid, None)
                if session is not None:
                    session.close()
            if not self._sessions:
                return None
            return max(self._sessions.values(), key=lambda s: s.last_used)


page_session_mgr = SessionManager(ttl_seconds=get_settings().browser_session_ttl_seconds)


def get_active_session():
    """Return the most recently used session, if one exists."""
    return page_session_mgr.get_most_recent()


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

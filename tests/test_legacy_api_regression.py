from fastapi.testclient import TestClient
from server import app

client = TestClient(app)

def test_visit_empty_url_returns_400():
    response = client.post("/api/visit", json={"url": ""})
    assert response.status_code == 400
    assert response.json()["error"] == "URL is required"

def test_auto_detect_empty_url_returns_400():
    response = client.post("/api/auto-detect", json={"url": ""})
    assert response.status_code == 400
    assert response.json()["error"] == "URL is required"

def test_test_selector_empty_selector_returns_400():
    response = client.post("/api/test-selector", json={"selector": ""})
    assert response.status_code == 400
    assert response.json()["error"] == "Selector is required"

def test_test_fields_empty_fields_returns_400():
    response = client.post("/api/test-fields", json={"fields": []})
    assert response.status_code == 400
    assert response.json()["error"] == "At least one field is required"

def test_page_html_empty_url_returns_400():
    response = client.post("/api/page-html", json={"url": ""})
    assert response.status_code == 400
    assert response.json()["error"] == "URL is required"

def test_generate_crawler_empty_url_returns_400():
    response = client.post("/api/generate-crawler", json={
        "url": "",
        "item_selector": "body",
        "fields": []
    })
    assert response.status_code == 400
    assert response.json()["error"] == "URL and item_selector are required"

def test_generate_crawler_empty_item_selector_returns_400():
    response = client.post("/api/generate-crawler", json={
        "url": "https://example.com",
        "item_selector": "",
        "fields": []
    })
    assert response.status_code == 400
    assert response.json()["error"] == "URL and item_selector are required"


def test_generate_crawler_accepts_legacy_aliases_and_auto_provider(monkeypatch):
    captured = {}

    class FakeResponse:
        content = "# generated crawler script"
        model = "fallback-model"
        usage = {"prompt_tokens": 10, "completion_tokens": 5}
        error = None

    class FakeClient:
        model = "fallback-model"

        def generate_with_system(self, system, user, model):
            captured["system"] = system
            captured["user"] = user
            captured["model"] = model
            return FakeResponse()

    monkeypatch.setattr("backend.legacy_routes.get_default_client", lambda: FakeClient())

    response = client.post("/api/generate-crawler", json={
        "url": "https://example.com/list",
        "item_selector": "article.card",
        "fields": [
            {"field_name": "title", "selector": "h2", "extraction_type": "text"},
            {"name": "link", "selector": "a", "type": "attr:href:abs"},
        ],
        "pagination_selector": "a.next",
        "pagination_strategy": "click_next",
        "max_pages": 3,
        "html_fragment": "<article>sample</article>",
        "llm_provider": "auto",
    })

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["filename"] == "crawler.py"
    assert data["model"] == "fallback-model"
    assert "Target URL" in data["prompt"]
    assert "https://example.com/list" in data["prompt"]
    assert "title: h2 > text" in data["prompt"]
    assert "link: a > attr:href:abs" in data["prompt"]
    assert "Page HTML Structure" in data["prompt"]
    assert captured["model"] == "fallback-model"
    assert "complete, working Playwright crawler" in captured["system"]


def test_generate_crawler_surfaces_llm_errors(monkeypatch):
    class FakeResponse:
        content = ""
        model = "broken-model"
        usage = None
        error = "upstream unavailable"

    class FakeClient:
        model = "broken-model"

        def generate_with_system(self, system, user, model):
            return FakeResponse()

    monkeypatch.setattr("backend.legacy_routes.get_llm_client", lambda **kwargs: FakeClient())
    monkeypatch.setattr("backend.legacy_routes.get_default_client", lambda: FakeClient())

    response = client.post("/api/generate-crawler", json={
        "url": "https://example.com/list",
        "item_selector": "article.card",
        "fields": [{"name": "title", "selector": "h2", "type": "text"}],
        "llm_provider": "openai",
    })

    assert response.status_code == 500
    assert response.json()["error"] == "upstream unavailable"


def test_picker_and_session_helpers_keep_legacy_error_contracts():
    picker_response = client.post("/api/picker-enable", json={"custom_roles": [" custom_field ", "", 12]})
    assert picker_response.status_code == 400
    assert picker_response.json()["error"] == "No active session. Please visit a page first."

    disable_response = client.post("/api/picker-disable", json={"session_id": "missing-session"})
    assert disable_response.status_code == 200
    assert disable_response.json() == {"success": True}

    clear_response = client.post("/api/clear-highlights", json={"session_id": "missing-session"})
    assert clear_response.status_code == 200
    assert clear_response.json() == {"success": True}

    close_response = client.post("/api/session/close", json={"session_id": "missing-session"})
    assert close_response.status_code == 200
    assert close_response.json() == {"success": False, "session_id": "missing-session"}

    keepalive_response = client.post("/api/session/keep-alive", json={"session_id": "missing-session"})
    assert keepalive_response.status_code == 404
    assert keepalive_response.json()["error"] == "Session not found"

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

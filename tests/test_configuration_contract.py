from pathlib import Path
import tomllib

from backend.core.settings import CrawlerWorkflowSettings


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_settings_reads_environment_over_project_env(monkeypatch):
    monkeypatch.setenv("BACKEND_PORT", "8111")
    monkeypatch.setenv("BROWSER_HEADLESS", "true")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("API_BASE_URL", "https://llm.example.test/v1")
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.setenv("SCRIPT_GENERATION_MAX_TOKENS", "321")
    monkeypatch.setenv("SCRIPT_REVIEW_MAX_TOKENS", "111")
    monkeypatch.setenv("DEFAULT_MAX_PAGES", "9")

    settings = CrawlerWorkflowSettings.from_env()

    assert settings.backend_port == 8111
    assert settings.browser_headless is True
    assert settings.llm_provider == "openai"
    assert settings.api_base_url == "https://llm.example.test/v1"
    assert settings.api_token == "test-token"
    assert settings.model_name == "test-model"
    assert settings.script_generation_max_tokens == 321
    assert settings.script_review_max_tokens == 111
    assert settings.default_max_pages == 9


def test_settings_default_script_token_limits_are_unset_when_not_configured(monkeypatch):
    monkeypatch.delenv("SCRIPT_GENERATION_MAX_TOKENS", raising=False)
    monkeypatch.delenv("SCRIPT_REVIEW_MAX_TOKENS", raising=False)

    settings = CrawlerWorkflowSettings.from_env()

    assert settings.script_generation_max_tokens is None
    assert settings.script_review_max_tokens is None


def test_settings_default_script_sandbox_timeout_is_longer_than_navigation_timeout(monkeypatch):
    monkeypatch.delenv("SCRIPT_SANDBOX_TIMEOUT_SECONDS", raising=False)

    settings = CrawlerWorkflowSettings.from_env()

    assert settings.script_sandbox_timeout_seconds == 60


def test_frontend_proxy_default_matches_backend_default_port():
    vite_config = (PROJECT_ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    frontend_env = (PROJECT_ROOT / "frontend" / ".env.development").read_text(encoding="utf-8")
    settings = CrawlerWorkflowSettings()
    expected_target = f"http://127.0.0.1:{settings.backend_port}"

    assert expected_target in vite_config
    assert f"CRAWLER_WORKFLOW_API_PROXY_TARGET={expected_target}" in frontend_env


def test_declared_python_modules_exist():
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    modules = pyproject["tool"]["setuptools"]["py-modules"]

    for module_name in modules:
        assert (PROJECT_ROOT / f"{module_name}.py").exists(), f"{module_name}.py is declared but missing"

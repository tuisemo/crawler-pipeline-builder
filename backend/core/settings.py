"""Runtime settings for crawler-workflow.

The project currently keeps configuration lightweight: environment variables
override values from the repository-level `.env` file, then built-in defaults
fill the gaps.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


def load_env_config(env_path: Path | None = None) -> dict[str, str]:
    """Load simple KEY=VALUE pairs from the project `.env` file."""
    path = env_path or DEFAULT_ENV_PATH
    config: dict[str, str] = {}
    if not path.exists():
        return config

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        config[key.strip()] = value.strip()
    return config


def _read_value(config: dict[str, str], key: str, default: str, *aliases: str) -> str:
    for candidate in (key, *aliases):
        value = os.environ.get(candidate)
        if value is not None and value.strip():
            return value.strip()
    for candidate in (key, *aliases):
        value = config.get(candidate)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def _read_int(config: dict[str, str], key: str, default: int, *aliases: str) -> int:
    raw = _read_value(config, key, str(default), *aliases)
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _read_bool(config: dict[str, str], key: str, default: bool, *aliases: str) -> bool:
    raw = _read_value(config, key, str(default), *aliases).strip().lower()
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    return default


@dataclass(frozen=True)
class CrawlerWorkflowSettings:
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    browser_headless: bool = False
    browser_session_ttl_seconds: int = 600
    llm_provider: str = "openai"
    api_base_url: str = ""
    api_token: str = ""
    model_name: str = "gpt-4"
    script_generation_max_tokens: int = 32000
    script_review_max_tokens: int = 32000
    default_max_steps: int = 100
    default_max_items: int = 50
    default_max_pages: int = 10
    default_output_mode: str = "memory"
    default_output_dir: str = "output"

    @classmethod
    def from_env(cls) -> "CrawlerWorkflowSettings":
        config = load_env_config()
        provider = _read_value(config, "LLM_PROVIDER", "openai", "PROVIDER")
        api_base_url = _read_value(config, "API_BASE_URL", "")
        model_name = _read_value(config, "MODEL_NAME", "")

        if provider == "vllm" or (api_base_url and "vllm" in api_base_url.lower()):
            provider = "vllm"
            if not model_name:
                model_name = "qwen3-30b-a3b-instruct"
        elif not model_name:
            model_name = "gpt-4"

        return cls(
            backend_host=_read_value(config, "BACKEND_HOST", "127.0.0.1", "CRAWLER_WORKFLOW_BACKEND_HOST"),
            backend_port=_read_int(config, "BACKEND_PORT", 8000, "CRAWLER_WORKFLOW_BACKEND_PORT"),
            browser_headless=_read_bool(config, "BROWSER_HEADLESS", False, "CRAWLER_WORKFLOW_BROWSER_HEADLESS"),
            browser_session_ttl_seconds=_read_int(
                config,
                "BROWSER_SESSION_TTL_SECONDS",
                600,
                "CRAWLER_WORKFLOW_BROWSER_SESSION_TTL_SECONDS",
            ),
            llm_provider=provider,
            api_base_url=api_base_url,
            api_token=_read_value(config, "API_TOKEN", ""),
            model_name=model_name,
            script_generation_max_tokens=_read_int(config, "SCRIPT_GENERATION_MAX_TOKENS", 32000),
            script_review_max_tokens=_read_int(config, "SCRIPT_REVIEW_MAX_TOKENS", 32000),
            default_max_steps=_read_int(config, "DEFAULT_MAX_STEPS", 100),
            default_max_items=_read_int(config, "DEFAULT_MAX_ITEMS", 50),
            default_max_pages=_read_int(config, "DEFAULT_MAX_PAGES", 10),
            default_output_mode=_read_value(config, "DEFAULT_OUTPUT_MODE", "memory"),
            default_output_dir=_read_value(config, "DEFAULT_OUTPUT_DIR", "output"),
        )


def get_settings() -> CrawlerWorkflowSettings:
    return CrawlerWorkflowSettings.from_env()

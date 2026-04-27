"""LLM client for sea-data.

Provides integration with OpenAI-compatible APIs (OpenAI + vLLM) for crawler script generation.
Supports loading configuration from .env file.
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def load_env_config() -> dict[str, str]:
    """Load configuration from .env file in project root."""
    env_path = Path(__file__).parent / ".env"
    config = {}
    
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    
    return config


# Load env config at module level
ENV_CONFIG = load_env_config()


@dataclass
class LLMResponse:
    """Response from LLM API."""
    content: str
    model: str = ""
    usage: dict[str, int] | None = None
    finish_reason: str | None = None
    error: str | None = None


@dataclass
class LLMConfig:
    """LLM provider configuration."""
    provider: str = "openai"
    api_key: str = ""
    base_url: str = ""
    model: str = "gpt-4"
    
    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Create config from environment variables or .env file."""
        # Priority: environment variable > .env file > defaults
        config = load_env_config()
        
        provider = os.environ.get("LLM_PROVIDER", config.get("PROVIDER", "openai"))
        
        # Handle vLLM/OpenAI compatible endpoints
        api_base = os.environ.get("API_BASE_URL", config.get("API_BASE_URL", ""))
        api_token = os.environ.get("API_TOKEN", config.get("API_TOKEN", ""))
        
        # Determine model based on provider
        model = os.environ.get("MODEL_NAME", config.get("MODEL_NAME", ""))
        
        if provider == "vllm" or (api_base and "vllm" in api_base.lower()):
            provider = "vllm"
            if not model:
                model = config.get("MODEL_NAME", "qwen3-30b-a3b-instruct")
        
        return cls(
            provider=provider,
            api_key=api_token,
            base_url=api_base,
            model=model
        )


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """Generate content from prompt."""
        pass

    @abstractmethod
    def generate_with_system(self, system: str, user: str, **kwargs) -> LLMResponse:
        """Generate content with system and user messages."""
        pass


class OpenAIClient(BaseLLMClient):
    """OpenAI API client (also works with vLLM and OpenAI-compatible endpoints)."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str = "gpt-4"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "") or ENV_CONFIG.get("API_TOKEN", "")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL", "") or ENV_CONFIG.get("API_BASE_URL", "")
        self.model = model or os.environ.get("MODEL_NAME", "") or ENV_CONFIG.get("MODEL_NAME", "gpt-4")

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """Generate content using OpenAI-compatible API."""
        try:
            import openai
        except ImportError:
            return LLMResponse(content="", error="OpenAI package not installed. Run: pip install openai")

        client_kwargs = {}
        if self.api_key:
            client_kwargs["api_key"] = self.api_key
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        
        # For vLLM, you might need to set base_url to the gateway URL
        # and ensure api_key is set appropriately

        try:
            client = openai.OpenAI(**client_kwargs)
            response = client.chat.completions.create(
                model=kwargs.get("model", self.model),
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", 0.2),
                max_tokens=kwargs.get("max_tokens", 4000)
            )
            if response.choices is None or len(response.choices) == 0:
                return LLMResponse(content="", error="LLM returned no choices")
            return LLMResponse(
                content=response.choices[0].message.content or "",
                model=response.model,
                usage={"prompt_tokens": response.usage.prompt_tokens, "completion_tokens": response.usage.completion_tokens} if response.usage is not None else None,
                finish_reason=response.choices[0].finish_reason,
            )
        except Exception as e:
            return LLMResponse(content="", error=str(e))

    def generate_with_system(self, system: str, user: str, **kwargs) -> LLMResponse:
        """Generate content with system and user messages."""
        try:
            import openai
        except ImportError:
            return LLMResponse(content="", error="OpenAI package not installed. Run: pip install openai")

        client_kwargs = {}
        if self.api_key:
            client_kwargs["api_key"] = self.api_key
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        try:
            client = openai.OpenAI(**client_kwargs)
            response = client.chat.completions.create(
                model=kwargs.get("model", self.model),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ],
                temperature=kwargs.get("temperature", 0.2),
                max_tokens=kwargs.get("max_tokens", 4000)
            )
            if response.choices is None or len(response.choices) == 0:
                return LLMResponse(content="", error="LLM returned no choices")
            return LLMResponse(
                content=response.choices[0].message.content or "",
                model=response.model,
                usage={"prompt_tokens": response.usage.prompt_tokens, "completion_tokens": response.usage.completion_tokens} if response.usage is not None else None,
                finish_reason=response.choices[0].finish_reason,
            )
        except Exception as e:
            return LLMResponse(content="", error=str(e))


class VLLMClient(OpenAIClient):
    """vLLM client - OpenAI-compatible, uses gateway URL and API token."""
    
    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str = "qwen3-30b-a3b-instruct"):
        # vLLM uses API_TOKEN from env
        api_key = api_key or os.environ.get("API_TOKEN", "") or ENV_CONFIG.get("API_TOKEN", "")
        base_url = base_url or os.environ.get("API_BASE_URL", "") or ENV_CONFIG.get("API_BASE_URL", "")
        model = model or os.environ.get("MODEL_NAME", "") or ENV_CONFIG.get("MODEL_NAME", "qwen3-30b-a3b-instruct")
        super().__init__(api_key=api_key, base_url=base_url, model=model)


def get_llm_client(provider: str = "auto", **kwargs) -> BaseLLMClient:
    """Get LLM client by provider name.

    Args:
        provider: "openai", "vllm", or "auto" (reads from env)
        **kwargs: Additional arguments passed to client

    Returns:
        LLM client instance
    """
    if provider == "auto":
        config = LLMConfig.from_env()
        provider = config.provider
    
    if provider.lower() in ("vllm",):
        return VLLMClient(**kwargs)
    else:
        return OpenAIClient(**kwargs)


def get_default_client() -> BaseLLMClient:
    """Get default LLM client based on environment configuration."""
    config = LLMConfig.from_env()
    
    if config.provider == "vllm":
        return VLLMClient(
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model
        )
    else:
        return OpenAIClient(
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model
        )


# System prompt for crawler generation
CRAWLER_SYSTEM_PROMPT = """You are an expert Python Web Scraping Engineer specializing in Playwright.

Your task is to generate complete, working Playwright crawler scripts based on user specifications.
When the user provides a deterministic reference skeleton, treat it as the required base implementation and improve it surgically instead of rewriting the crawler architecture from scratch.

Key requirements:
1. Use Playwright's sync_api (sync_playwright)
2. Handle pagination with proper waits and verification
3. Output structured JSON data
4. Include error handling and retries
5. Use anti-detection measures (realistic waits, viewport, user-agent)
6. Handle relative URLs properly with urljoin
7. Treat the deterministic execution plan as the single source of truth; do not invent control flow, persistence behavior, or selectors that conflict with it.
8. Keep selectors compatible with standard CSS selector execution in Playwright (`page.query_selector`, `page.query_selector_all`, `locator`) and DOM APIs (`querySelector`, `querySelectorAll`).

Output format:
- Provide the complete Python script
- Include necessary imports
- The script should be self-contained and runnable

Common patterns:
- For clicking next page: Use locator with scroll_into_view_if_needed first, then click
- For extracting text: inner_text() method
- For URLs: get_attribute('href') and resolve with urljoin
- For waiting: wait_for_selector with appropriate timeout
- For pagination: Verify content changed after click (compare first item)
- Preserve stable helper functions, persistence helpers, and output contracts when a baseline script already includes them.
- If the output mode is `memory`, keep records in memory and do not invent file or SQLite persistence.
- If pagination strategy is `none` or selector is blank, do not invent pagination behavior.

Always verify your selectors will work on the actual page structure provided."""


# AI Enhancement Prompts for various features
FIELD_INFERENCE_PROMPT = """Given this HTML fragment from a web page, infer the semantic meaning of each element.

HTML:
{html_fragment}

Task:
1. Identify the main list/grid container
2. For each list item, determine:
   - What data fields it contains (title, price, image, date, etc.)
   - The CSS selector path to each field
   - The best extraction method (text, attribute, etc.)
3. Suggest a field name for each extracted value
4. Every selector you return MUST be a standard CSS selector that can be executed directly in Playwright via
   `page.query_selector(...)`, `page.query_selector_all(...)`, `locator(...)`, and in DOM APIs like
   `document.querySelector(...)` / `querySelectorAll(...)`.
5. Do NOT return Playwright-only locator expressions or helper syntax such as `get_by_role(...)`,
   `get_by_text(...)`, `locator(...)`, `nth=`, `>>`, `:has-text(...)`, `text=`, or XPath selectors.
6. Prefer short, stable, semantic CSS selectors based on tag name, stable class names, ID, and data attributes.

Output format:
```json
{{
  "item_selector": "suggested CSS selector for list container",
  "fields": [
    {{"name": "title", "selector": "h2", "type": "text", "confidence": 0.9}},
    {{"name": "price", "selector": ".price", "type": "text", "confidence": 0.8}}
  ]
}}
```"""

SELECTOR_OPTIMIZATION_PROMPT = """Given an initial CSS selector and sample HTML, optimize it to be more robust.

Initial selector: {initial_selector}
Sample HTML:
{html_fragment}

Task:
1. Analyze why the current selector might be fragile
2. Suggest a more robust alternative
3. Consider: stable classes, semantic tags, avoiding nth-child with high numbers
4. The optimized selector MUST remain a standard CSS selector that can be executed directly in Playwright via
   `page.query_selector(...)`, `page.query_selector_all(...)`, `locator(...)`, and in DOM APIs like
   `document.querySelector(...)` / `querySelectorAll(...)`.
5. Do NOT return Playwright-only locator expressions or helper syntax such as `get_by_role(...)`,
   `get_by_text(...)`, `locator(...)`, `nth=`, `>>`, `:has-text(...)`, `text=`, or XPath selectors.
6. Prefer selectors built from stable tag/class/id/data-attribute combinations that are likely to survive minor DOM changes.

Output format:
```json
{{
  "optimized_selector": "improved CSS selector",
  "reason": "explanation of improvements"
}}
```"""

PAGINATION_ANALYSIS_PROMPT = """Given HTML content containing pagination elements, analyze the pagination pattern and extract highly robust selectors.

HTML:
{html_fragment}

Task:
1. Identify the pagination container and the specific "Next Page" (下一页) or "Load More" (加载更多) element.
2. Determine the exact pagination strategy:
   - 'click_next': Standard pagination with a "Next" button/link.
   - 'infinite_scroll': No button, triggers on scroll.
   - 'load_more': Explicit button to append items.
   - 'none': No pagination found.
3. Provide a ROBUST CSS selector for the next/load-more button. Prefer semantic classes (e.g., '.next', '.pagination-next', 'a[rel="next"]'), ID, or stable data-attributes over brittle nth-child paths.
4. Account for multi-language text variations (Next/Load More, 下一页/加载更多).
5. Every selector you return MUST be a standard CSS selector that can be executed directly in Playwright via
   `page.query_selector(...)`, `page.query_selector_all(...)`, `locator(...)`, and in DOM APIs like
   `document.querySelector(...)` / `querySelectorAll(...)`.
6. Do NOT return Playwright-only locator expressions or helper syntax such as `get_by_role(...)`,
   `get_by_text(...)`, `locator(...)`, `nth=`, `>>`, `:has-text(...)`, `text=`, or XPath selectors.

Output format:
```json
{{
  "pagination_strategy": "click_next|infinite_scroll|load_more|none",
  "next_button_selector": "robust CSS selector for next button",
  "page_number_selectors": ["list of page number selectors"],
  "reason": "Explain why this selector and strategy were chosen",
  "confidence": 0.0-1.0
}}
```"""

DATA_CLEANING_PROMPT = """Given extracted raw data, clean and normalize it.

Raw data:
{raw_data}

Data type: {data_type}

Task:
1. Clean the data (remove extra whitespace, special characters)
2. Normalize to standard format based on data_type
3. Return cleaned value

Supported data_types:
- price: Extract numeric value, handle currency symbols
- date: Convert to ISO format (YYYY-MM-DD)
- rating: Extract number, normalize to 0-5 scale
- count: Extract integer, handle K/M suffixes (1.2K -> 1200)
- phone: Extract digits only
- email: Validate and return
- url: Return as-is or resolve to absolute

Output format:
```json
{{
  "cleaned_value": "normalized result",
  "confidence": 0.0-1.0
}}
```"""

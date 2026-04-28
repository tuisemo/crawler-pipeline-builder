"""LLM client for crawler-workflow.

Provides integration with OpenAI-compatible APIs (OpenAI + vLLM) for crawler script generation.
Supports loading configuration from .env file.
"""

import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from backend.core.app_logging import audit_event
from backend.core.settings import get_settings, load_env_config


def _should_retry_without_response_format(error: Exception) -> bool:
    message = str(error).lower()
    markers = (
        "response_format",
        "json_object",
        "json schema",
        "json_schema",
        "unsupported",
        "extra_forbidden",
        "extra inputs are not permitted",
        "unknown field",
        "unknown parameter",
    )
    return any(marker in message for marker in markers)


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
        settings = get_settings()
        return cls(
            provider=settings.llm_provider,
            api_key=settings.api_token,
            base_url=settings.api_base_url,
            model=settings.model_name,
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

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        settings = get_settings()
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "") or settings.api_token
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL", "") or settings.api_base_url
        self.model = model or os.environ.get("MODEL_NAME", "") or settings.model_name

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

        request_id = str(kwargs.get("request_id") or uuid.uuid4().hex[:12])
        request_name = str(kwargs.get("request_name") or "generic_generate")
        audit_event(
            "llm_request",
            request_id=request_id,
            request_name=request_name,
            method="generate",
            model=kwargs.get("model", self.model),
            temperature=kwargs.get("temperature", 0.2),
            max_tokens=kwargs.get("max_tokens", 16000),
            response_format=kwargs.get("response_format"),
            prompt=prompt,
        )

        try:
            client = openai.OpenAI(**client_kwargs)
            create_kwargs = {
                "model": kwargs.get("model", self.model),
                "messages": [{"role": "user", "content": prompt}],
                "temperature": kwargs.get("temperature", 0.2),
                "max_tokens": kwargs.get("max_tokens", 16000),
            }
            response_format = kwargs.get("response_format")
            if response_format is not None:
                create_kwargs["response_format"] = response_format
            response = client.chat.completions.create(**create_kwargs)
            if response.choices is None or len(response.choices) == 0:
                audit_event(
                    "llm_empty_choices",
                    request_id=request_id,
                    request_name=request_name,
                    method="generate",
                    model=kwargs.get("model", self.model),
                )
                return LLMResponse(content="", error="LLM returned no choices")
            llm_response = LLMResponse(
                content=response.choices[0].message.content or "",
                model=response.model,
                usage={"prompt_tokens": response.usage.prompt_tokens, "completion_tokens": response.usage.completion_tokens} if response.usage is not None else None,
                finish_reason=response.choices[0].finish_reason,
            )
            audit_event(
                "llm_response",
                request_id=request_id,
                request_name=request_name,
                method="generate",
                model=llm_response.model,
                usage=llm_response.usage,
                finish_reason=llm_response.finish_reason,
                content=llm_response.content,
            )
            return llm_response
        except Exception as e:
            if kwargs.get("response_format") is not None and _should_retry_without_response_format(e):
                audit_event(
                    "llm_response_format_retry",
                    request_id=request_id,
                    request_name=request_name,
                    method="generate",
                    error=str(e),
                )
                try:
                    client = openai.OpenAI(**client_kwargs)
                    response = client.chat.completions.create(
                        model=kwargs.get("model", self.model),
                        messages=[{"role": "user", "content": prompt}],
                        temperature=kwargs.get("temperature", 0.2),
                        max_tokens=kwargs.get("max_tokens", 16000),
                    )
                    if response.choices is None or len(response.choices) == 0:
                        audit_event(
                            "llm_empty_choices",
                            request_id=request_id,
                            request_name=request_name,
                            method="generate",
                            model=kwargs.get("model", self.model),
                        )
                        return LLMResponse(content="", error="LLM returned no choices")
                    llm_response = LLMResponse(
                        content=response.choices[0].message.content or "",
                        model=response.model,
                        usage={"prompt_tokens": response.usage.prompt_tokens, "completion_tokens": response.usage.completion_tokens} if response.usage is not None else None,
                        finish_reason=response.choices[0].finish_reason,
                    )
                    audit_event(
                        "llm_response",
                        request_id=request_id,
                        request_name=request_name,
                        method="generate",
                        model=llm_response.model,
                        usage=llm_response.usage,
                        finish_reason=llm_response.finish_reason,
                        content=llm_response.content,
                    )
                    return llm_response
                except Exception as retry_error:
                    audit_event(
                        "llm_error",
                        request_id=request_id,
                        request_name=request_name,
                        method="generate",
                        error=str(retry_error),
                    )
                    return LLMResponse(content="", error=str(retry_error))
            audit_event(
                "llm_error",
                request_id=request_id,
                request_name=request_name,
                method="generate",
                error=str(e),
            )
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

        request_id = str(kwargs.get("request_id") or uuid.uuid4().hex[:12])
        request_name = str(kwargs.get("request_name") or "system_generate")
        audit_event(
            "llm_request",
            request_id=request_id,
            request_name=request_name,
            method="generate_with_system",
            model=kwargs.get("model", self.model),
            temperature=kwargs.get("temperature", 0.2),
            max_tokens=kwargs.get("max_tokens", 16000),
            response_format=kwargs.get("response_format"),
            system=system,
            user=user,
        )

        try:
            client = openai.OpenAI(**client_kwargs)
            create_kwargs = {
                "model": kwargs.get("model", self.model),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ],
                "temperature": kwargs.get("temperature", 0.2),
                "max_tokens": kwargs.get("max_tokens", 16000),
            }
            response_format = kwargs.get("response_format")
            if response_format is not None:
                create_kwargs["response_format"] = response_format
            response = client.chat.completions.create(**create_kwargs)
            if response.choices is None or len(response.choices) == 0:
                audit_event(
                    "llm_empty_choices",
                    request_id=request_id,
                    request_name=request_name,
                    method="generate_with_system",
                    model=kwargs.get("model", self.model),
                )
                return LLMResponse(content="", error="LLM returned no choices")
            llm_response = LLMResponse(
                content=response.choices[0].message.content or "",
                model=response.model,
                usage={"prompt_tokens": response.usage.prompt_tokens, "completion_tokens": response.usage.completion_tokens} if response.usage is not None else None,
                finish_reason=response.choices[0].finish_reason,
            )
            audit_event(
                "llm_response",
                request_id=request_id,
                request_name=request_name,
                method="generate_with_system",
                model=llm_response.model,
                usage=llm_response.usage,
                finish_reason=llm_response.finish_reason,
                content=llm_response.content,
            )
            return llm_response
        except Exception as e:
            if kwargs.get("response_format") is not None and _should_retry_without_response_format(e):
                audit_event(
                    "llm_response_format_retry",
                    request_id=request_id,
                    request_name=request_name,
                    method="generate_with_system",
                    error=str(e),
                )
                try:
                    client = openai.OpenAI(**client_kwargs)
                    response = client.chat.completions.create(
                        model=kwargs.get("model", self.model),
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": user}
                        ],
                        temperature=kwargs.get("temperature", 0.2),
                        max_tokens=kwargs.get("max_tokens", 16000),
                    )
                    if response.choices is None or len(response.choices) == 0:
                        audit_event(
                            "llm_empty_choices",
                            request_id=request_id,
                            request_name=request_name,
                            method="generate_with_system",
                            model=kwargs.get("model", self.model),
                        )
                        return LLMResponse(content="", error="LLM returned no choices")
                    llm_response = LLMResponse(
                        content=response.choices[0].message.content or "",
                        model=response.model,
                        usage={"prompt_tokens": response.usage.prompt_tokens, "completion_tokens": response.usage.completion_tokens} if response.usage is not None else None,
                        finish_reason=response.choices[0].finish_reason,
                    )
                    audit_event(
                        "llm_response",
                        request_id=request_id,
                        request_name=request_name,
                        method="generate_with_system",
                        model=llm_response.model,
                        usage=llm_response.usage,
                        finish_reason=llm_response.finish_reason,
                        content=llm_response.content,
                    )
                    return llm_response
                except Exception as retry_error:
                    audit_event(
                        "llm_error",
                        request_id=request_id,
                        request_name=request_name,
                        method="generate_with_system",
                        error=str(retry_error),
                    )
                    return LLMResponse(content="", error=str(retry_error))
            audit_event(
                "llm_error",
                request_id=request_id,
                request_name=request_name,
                method="generate_with_system",
                error=str(e),
            )
            return LLMResponse(content="", error=str(e))


class VLLMClient(OpenAIClient):
    """vLLM client - OpenAI-compatible, uses gateway URL and API token."""
    
    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        settings = get_settings()
        api_key = api_key or os.environ.get("API_TOKEN", "") or settings.api_token
        base_url = base_url or os.environ.get("API_BASE_URL", "") or settings.api_base_url
        model = model or os.environ.get("MODEL_NAME", "") or settings.model_name
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
FIELD_INFERENCE_PROMPT = """Analyze the HTML fragment below and extract structured field selectors for a web scraper.

HTML:
{html_fragment}

## Selector Precision Rules (CRITICAL)
You MUST produce **progressively-converging** (逐级收敛) selectors that are globally unambiguous on the page:

1. **item_selector** — a CSS selector that matches ONLY the repeating list items, not any other elements.
   - Prefer a scoped path: `<ancestor> > <tag>.<stable-class>` (e.g. `ul.news-list > li`, `div.results-grid > article`).
   - If the item has a unique class, verify it is not shared by navigation, sidebar, or footer elements.
   - Do NOT return a bare tag like `li` or `div` that matches hundreds of unrelated elements.

2. **field selectors** — relative to each list item element (i.e. evaluated inside the item, not the whole document).
   - Use `:scope > ...` or a short relative path when possible (e.g. `:scope > a > .title`, `.card-body > h3.title`).
   - If the class name could appear globally (e.g. `.title`, `.date`, `.name`), prefix it with the nearest stable ancestor: `div.card-body > span.date`.
   - Avoid bare generic selectors like `p`, `span`, `div` that match many things.

3. Every selector MUST be a **standard CSS selector** compatible with `querySelector` / `querySelectorAll` and Playwright `locator()`.
4. Do NOT return Playwright-only locator expressions or helper syntax such as `get_by_role(...)`, `get_by_text(...)`, `nth=`, `>>`, `:has-text(...)`, `text=`, or XPath selectors.

## Field Coverage
For each repeating item, extract ALL meaningful fields present:
- `title` — main heading or article name (text)
- `link` — the primary anchor URL (attr:href)
- `publish_date` — publication or update date/time (text)
- `summary` — excerpt or description if present (text)
- `image` — thumbnail image if present (attr:src or attr:data-src)
- `source` — author, category, or source tag if present (text)
- Any other domain-specific fields visible in the HTML

Snake_case field names. Aim for 3–6 fields per item."""

SELECTOR_OPTIMIZATION_PROMPT = """Optimize the CSS selector below to be globally unambiguous and resilient to minor DOM changes.

Initial selector: {initial_selector}

Sample HTML:
{html_fragment}

## Optimization Steps
1. **Diagnose ambiguity**: count how many elements on the page the current selector could match. If more than the expected item count, it is too broad.
2. **Converge progressively**: build a scoped path by walking UP the DOM tree to the nearest stable semantic ancestor (landmark element, unique ID, or stable class), then walk DOWN to the target.
   - Good: `section.news-container > ul > li.news-item`
   - Bad: `.news-item` (naked class, may appear elsewhere)
3. **Prefer stable attributes**: IDs (if truly unique), stable class names, `data-*` attributes, or semantic HTML tags.
4. **Trim redundancy**: remove intermediate nodes that don't add disambiguation value.
5. The optimized selector MUST be a standard CSS selector compatible with `querySelector` / `querySelectorAll` and Playwright `locator()`.
6. Do NOT return Playwright-only locator expressions or helper syntax such as `get_by_role(...)`, `get_by_text(...)`, `nth=`, `>>`, `:has-text(...)`, `text=`, or XPath selectors."""

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
3. Provide a ROBUST CSS selector for the single actionable next/load-more control, not for the whole pagination container and not for the whole set of page number buttons.
4. If the HTML includes a `PAGINATION_CONTROL_SUMMARY`, use it as strong evidence to distinguish:
   - the current page indicator,
   - numbered page buttons,
   - the real next/previous/load-more control.
5. For `click_next`, `next_button_selector` must target the concrete next-page control only.
   It must NOT be a selector that matches:
   - all pagination anchors or buttons,
   - all numbered page buttons,
   - the entire pagination container.
6. Only populate `page_number_selectors` with selectors for numbered page buttons. Do not put the next/load-more selector into `page_number_selectors`.
7. If there is no distinct next/load-more control, return `pagination_strategy: "none"` or an empty `next_button_selector` rather than guessing a broad selector.
8. Account for multi-language text variations (Next/Load More, 下一页/加载更多).
9. Every selector you return MUST be a standard CSS selector that can be executed directly in Playwright via
   `page.query_selector(...)`, `page.query_selector_all(...)`, `locator(...)`, and in DOM APIs like
   `document.querySelector(...)` / `querySelectorAll(...)`.
10. Do NOT return Playwright-only locator expressions or helper syntax such as `get_by_role(...)`,
   `get_by_text(...)`, `locator(...)`, `nth=`, `>>`, `:has-text(...)`, `text=`, or XPath selectors.
11. Prefer semantic next-button selectors such as `.next`, `.pagination-next`, `a[rel="next"]`, `[aria-label*="next" i]`, or other stable attributes before considering generic position-based selectors.

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

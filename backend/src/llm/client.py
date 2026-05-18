"""LLM client for crawler-workflow.

Provides integration with OpenAI-compatible APIs (OpenAI + vLLM) for crawler script generation.
Supports loading configuration from .env file.
"""

import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from core.app_logging import audit_event
from core.settings import get_settings
from prompts.tasks.assist_tasks import (
    FIELD_INFERENCE_PROMPT_TEMPLATE as FIELD_INFERENCE_PROMPT,
    PAGINATION_ANALYSIS_PROMPT_TEMPLATE as PAGINATION_ANALYSIS_PROMPT,
    SELECTOR_OPTIMIZATION_PROMPT_TEMPLATE as SELECTOR_OPTIMIZATION_PROMPT,
)
from prompts.tasks.crawler_system import CRAWLER_SYSTEM_PROMPT

_DEFAULT_TIMEOUT = 120


def _should_retry_without_response_format(error: Exception) -> bool:
    """Check if the error indicates response_format is unsupported by the provider."""
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


def _parse_usage(usage: Any) -> dict[str, int] | None:
    """Extract token usage dict from an OpenAI usage object, or return None."""
    if usage is None:
        return None
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
    }


def _strip_internal_request_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Remove client-internal tracing kwargs before forwarding API options."""
    forwarded = dict(kwargs)
    forwarded.pop("request_id", None)
    forwarded.pop("request_name", None)
    return forwarded


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
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazily create and cache the OpenAI client instance."""
        if self._client is None:
            import openai

            client_kwargs: dict[str, Any] = {"timeout": _DEFAULT_TIMEOUT}
            if self.api_key:
                client_kwargs["api_key"] = self.api_key
            if self.base_url:
                client_kwargs["base_url"] = self.base_url
            self._client = openai.OpenAI(**client_kwargs)
        return self._client

    def _build_create_kwargs(self, messages: list[dict[str, str]], **kwargs) -> dict[str, Any]:
        """Build keyword arguments for chat.completions.create."""
        create_kwargs: dict[str, Any] = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.2),
        }
        max_tokens = kwargs.get("max_tokens")
        if isinstance(max_tokens, int) and max_tokens > 0:
            create_kwargs["max_tokens"] = max_tokens
        response_format = kwargs.get("response_format")
        if response_format is not None:
            create_kwargs["response_format"] = response_format
        return create_kwargs

    @staticmethod
    def _parse_response(response: Any) -> LLMResponse:
        """Parse an OpenAI chat completion response into an LLMResponse."""
        return LLMResponse(
            content=response.choices[0].message.content or "",
            model=response.model,
            usage=_parse_usage(response.usage),
            finish_reason=response.choices[0].finish_reason,
        )

    def _call_api(
        self,
        messages: list[dict[str, str]],
        method: str,
        request_id: str,
        request_name: str,
        **kwargs,
    ) -> LLMResponse:
        """Execute a chat completion API call with retry-on-response-format-error logic."""
        try:
            import openai  # noqa: F401 — verify package is available
        except ImportError:
            return LLMResponse(content="", error="OpenAI package not installed. Run: pip install openai")

        try:
            client = self._get_client()
            create_kwargs = self._build_create_kwargs(messages, **kwargs)
            response = client.chat.completions.create(**create_kwargs)

            if response.choices is None or len(response.choices) == 0:
                audit_event(
                    "llm_empty_choices",
                    request_id=request_id,
                    request_name=request_name,
                    method=method,
                    model=kwargs.get("model", self.model),
                )
                return LLMResponse(content="", error="LLM returned no choices")

            llm_response = self._parse_response(response)
            audit_event(
                "llm_response",
                request_id=request_id,
                request_name=request_name,
                method=method,
                model=llm_response.model,
                usage=llm_response.usage,
                finish_reason=llm_response.finish_reason,
                content=llm_response.content,
            )
            return llm_response
        # Intentional broad catch: this method must never raise.
        # All errors are converted to LLMResponse.error for callers to inspect.
        except Exception as e:
            return self._handle_api_error(e, messages, method, request_id, request_name, **kwargs)

    def _handle_api_error(
        self,
        error: Exception,
        messages: list[dict[str, str]],
        method: str,
        request_id: str,
        request_name: str,
        **kwargs,
    ) -> LLMResponse:
        """Handle an API error, retrying without response_format when appropriate."""
        if kwargs.get("response_format") is not None and _should_retry_without_response_format(error):
            audit_event(
                "llm_response_format_retry",
                request_id=request_id,
                request_name=request_name,
                method=method,
                error=str(error),
            )
            retry_kwargs = {k: v for k, v in kwargs.items() if k != "response_format"}
            try:
                client = self._get_client()
                create_kwargs = self._build_create_kwargs(messages, **retry_kwargs)
                response = client.chat.completions.create(**create_kwargs)

                if response.choices is None or len(response.choices) == 0:
                    audit_event(
                        "llm_empty_choices",
                        request_id=request_id,
                        request_name=request_name,
                        method=method,
                        model=kwargs.get("model", self.model),
                    )
                    return LLMResponse(content="", error="LLM returned no choices")

                llm_response = self._parse_response(response)
                audit_event(
                    "llm_response",
                    request_id=request_id,
                    request_name=request_name,
                    method=method,
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
                    method=method,
                    error=str(retry_error),
                )
                return LLMResponse(content="", error=str(retry_error))

        audit_event(
            "llm_error",
            request_id=request_id,
            request_name=request_name,
            method=method,
            error=str(error),
        )
        return LLMResponse(content="", error=str(error))

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """Generate content using OpenAI-compatible API."""
        messages = [{"role": "user", "content": prompt}]
        request_id = str(kwargs.get("request_id") or uuid.uuid4().hex[:12])
        request_name = str(kwargs.get("request_name") or "generic_generate")
        api_kwargs = _strip_internal_request_kwargs(kwargs)
        audit_event(
            "llm_request",
            request_id=request_id,
            request_name=request_name,
            method="generate",
            model=kwargs.get("model", self.model),
            temperature=kwargs.get("temperature", 0.2),
            max_tokens=kwargs.get("max_tokens"),
            response_format=kwargs.get("response_format"),
            prompt=prompt,
        )
        return self._call_api(messages, "generate", request_id, request_name, **api_kwargs)

    def generate_with_system(self, system: str, user: str, **kwargs) -> LLMResponse:
        """Generate content with system and user messages."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        request_id = str(kwargs.get("request_id") or uuid.uuid4().hex[:12])
        request_name = str(kwargs.get("request_name") or "system_generate")
        api_kwargs = _strip_internal_request_kwargs(kwargs)
        audit_event(
            "llm_request",
            request_id=request_id,
            request_name=request_name,
            method="generate_with_system",
            model=kwargs.get("model", self.model),
            temperature=kwargs.get("temperature", 0.2),
            max_tokens=kwargs.get("max_tokens"),
            response_format=kwargs.get("response_format"),
            system=system,
            user=user,
        )
        return self._call_api(messages, "generate_with_system", request_id, request_name, **api_kwargs)


class VLLMClient(OpenAIClient):
    """vLLM client - OpenAI-compatible, uses gateway URL and API token."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        settings = get_settings()
        api_key = api_key or os.environ.get("API_TOKEN", "") or settings.api_token
        base_url = base_url or os.environ.get("API_BASE_URL", "") or settings.api_base_url
        model = model or os.environ.get("MODEL_NAME", "") or settings.model_name
        super().__init__(api_key=api_key, base_url=base_url, model=model)


def get_llm_client(provider: str = "auto", **kwargs) -> BaseLLMClient:
    """Get LLM client by provider name."""
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
            model=config.model,
        )
    else:
        return OpenAIClient(
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
        )

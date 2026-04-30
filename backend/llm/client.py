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
from backend.core.settings import get_settings
from backend.prompts.tasks.assist_tasks import (
    FIELD_INFERENCE_PROMPT_TEMPLATE as FIELD_INFERENCE_PROMPT,
    PAGINATION_ANALYSIS_PROMPT_TEMPLATE as PAGINATION_ANALYSIS_PROMPT,
    SELECTOR_OPTIMIZATION_PROMPT_TEMPLATE as SELECTOR_OPTIMIZATION_PROMPT,
)
from backend.prompts.tasks.crawler_system import CRAWLER_SYSTEM_PROMPT


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

    @staticmethod
    def _apply_optional_max_tokens(create_kwargs: dict[str, Any], kwargs: dict[str, Any]) -> None:
        max_tokens = kwargs.get("max_tokens")
        if isinstance(max_tokens, int) and max_tokens > 0:
            create_kwargs["max_tokens"] = max_tokens

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
            max_tokens=kwargs.get("max_tokens"),
            response_format=kwargs.get("response_format"),
            prompt=prompt,
        )

        try:
            client = openai.OpenAI(**client_kwargs)
            create_kwargs = {
                "model": kwargs.get("model", self.model),
                "messages": [{"role": "user", "content": prompt}],
                "temperature": kwargs.get("temperature", 0.2),
            }
            self._apply_optional_max_tokens(create_kwargs, kwargs)
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
                        **({"max_tokens": kwargs.get("max_tokens")} if isinstance(kwargs.get("max_tokens"), int) and kwargs.get("max_tokens") > 0 else {}),
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
            max_tokens=kwargs.get("max_tokens"),
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
            }
            self._apply_optional_max_tokens(create_kwargs, kwargs)
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
                        **({"max_tokens": kwargs.get("max_tokens")} if isinstance(kwargs.get("max_tokens"), int) and kwargs.get("max_tokens") > 0 else {}),
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



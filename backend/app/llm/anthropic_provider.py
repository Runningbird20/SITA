"""A real HTTP client against the Anthropic Messages API. See DEF.md §
Phase 6 "Post-roadmap addition".

Not OpenAI-compatible — different auth header, a required API version
header, and a different response envelope — so this is its own class
rather than a subclass of OpenAIProvider. Synchronous (httpx.Client, not
AsyncClient), matching this project's fully synchronous architecture. No
official SDK: hand-rolled, same reasoning as OllamaProvider.
"""

import httpx

from app.core.config import get_settings
from app.llm.base import LLMProvider
from app.llm.exceptions import LLMProviderError, LLMTimeoutError
from app.llm.types import LLMConfig, RawCompletion

_ANTHROPIC_API_VERSION = "2023-06-01"


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        settings = get_settings()
        self._base_url = base_url or settings.anthropic_base_url
        self._api_key = api_key or settings.anthropic_api_key

    def _complete(self, prompt: str, config: LLMConfig) -> RawCompletion:
        try:
            response = httpx.post(
                f"{self._base_url}/v1/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": _ANTHROPIC_API_VERSION,
                },
                json={
                    "model": config.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": config.temperature,
                    # Required by Anthropic's API, unlike OpenAI's (which
                    # defaults it) — no equivalent of a missing-value fallback.
                    "max_tokens": config.max_tokens,
                },
                timeout=config.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(str(exc)) from exc

        data = response.json()
        content_blocks = data.get("content") or []
        text = "".join(
            block.get("text", "") for block in content_blocks if block.get("type") == "text"
        )
        usage = data.get("usage") or {}
        return RawCompletion(
            text=text,
            prompt_tokens=usage.get("input_tokens"),
            completion_tokens=usage.get("output_tokens"),
        )

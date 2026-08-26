"""An OpenAI-compatible provider — covers real OpenAI *and* LM Studio,
whose local server speaks the same `/chat/completions` protocol. See
DEF.md § Phase 6 "Post-roadmap addition".

Synchronous (httpx.Client, not AsyncClient) to match this project's fully
synchronous architecture — no other module uses asyncio. No official SDK:
hand-rolled, same reasoning as OllamaProvider.
"""

import httpx

from app.core.config import get_settings
from app.llm.base import LLMProvider
from app.llm.exceptions import LLMProviderError, LLMTimeoutError
from app.llm.types import LLMConfig, RawCompletion


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        settings = get_settings()
        self._base_url = base_url or settings.openai_base_url
        self._api_key = api_key or settings.openai_api_key

    def _complete(self, prompt: str, config: LLMConfig) -> RawCompletion:
        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": config.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": config.temperature,
                    "max_tokens": config.max_tokens,
                    # Best-effort: real OpenAI models honor this; some
                    # OpenAI-compatible local servers (LM Studio included,
                    # depending on the loaded model) may ignore it. Every
                    # prompt already asks explicitly for JSON-only output
                    # (see app/triage/prompts.py), so this isn't the only
                    # thing enforcing the shape — the shared validation
                    # step downstream is.
                    "response_format": {"type": "json_object"},
                },
                timeout=config.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(str(exc)) from exc

        data = response.json()
        choice = data["choices"][0]["message"]
        usage = data.get("usage") or {}
        return RawCompletion(
            text=choice.get("content") or "",
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )


class LMStudioProvider(OpenAIProvider):
    """Identical request/response handling to OpenAIProvider — LM Studio's
    local server speaks the same protocol — this subclass exists only so
    `AnalysisResult.provider` records "lm_studio", not "openai", for
    correct provenance. See DEF.md § Phase 6 "Post-roadmap addition".
    """

    name = "lm_studio"

    def __init__(self, base_url: str | None = None):
        settings = get_settings()
        super().__init__(
            base_url=base_url or settings.lm_studio_base_url,
            # LM Studio doesn't validate the key — any non-empty string
            # satisfies clients that require an Authorization header.
            api_key="lm-studio",
        )

"""A real HTTP client against a local Ollama instance. See DEF.md § Phase 6.

Synchronous (httpx.Client, not AsyncClient) to match this project's fully
synchronous architecture — no other module uses asyncio.
"""

import httpx

from app.core.config import get_settings
from app.llm.base import LLMProvider
from app.llm.exceptions import LLMProviderError, LLMTimeoutError
from app.llm.types import LLMConfig, RawCompletion


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str | None = None):
        settings = get_settings()
        self._base_url = base_url or settings.ollama_base_url
        self._repeat_penalty = settings.ollama_repeat_penalty

    def _complete(self, prompt: str, config: LLMConfig) -> RawCompletion:
        try:
            response = httpx.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": config.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": config.temperature,
                        "num_predict": config.max_tokens,
                        "repeat_penalty": self._repeat_penalty,
                    },
                },
                timeout=config.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(str(exc)) from exc

        data = response.json()
        return RawCompletion(
            text=data.get("response", ""),
            prompt_tokens=data.get("prompt_eval_count"),
            completion_tokens=data.get("eval_count"),
        )

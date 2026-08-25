"""The entire "swapping providers requires no code changes elsewhere"
mechanism: callers use get_llm_provider() / default_llm_config() and never
import a concrete provider class directly. See DEF.md § Phase 6.
"""

from app.core.config import get_settings
from app.llm.base import LLMProvider
from app.llm.mock_provider import MockProvider
from app.llm.ollama_provider import OllamaProvider
from app.llm.types import LLMConfig


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider == "ollama":
        return OllamaProvider()
    return MockProvider()


def default_llm_config() -> LLMConfig:
    settings = get_settings()
    return LLMConfig(
        model=settings.ollama_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout_seconds=settings.llm_request_timeout_seconds,
        max_retries=settings.llm_max_retries,
        retry_backoff_seconds=settings.llm_retry_backoff_seconds,
    )

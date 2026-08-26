"""The entire "swapping providers requires no code changes elsewhere"
mechanism: callers use get_llm_provider() / default_llm_config() and never
import a concrete provider class directly. See DEF.md § Phase 6 and its
"Post-roadmap addition" (openai/anthropic/lm_studio).
"""

from app.core.config import get_settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LLMProvider
from app.llm.mock_provider import MockProvider
from app.llm.ollama_provider import OllamaProvider
from app.llm.openai_provider import LMStudioProvider, OpenAIProvider
from app.llm.types import LLMConfig

_MODEL_BY_PROVIDER = {
    "ollama": lambda s: s.ollama_model,
    "lm_studio": lambda s: s.lm_studio_model,
    "openai": lambda s: s.openai_model,
    "anthropic": lambda s: s.anthropic_model,
}


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    match settings.llm_provider:
        case "ollama":
            return OllamaProvider()
        case "lm_studio":
            return LMStudioProvider()
        case "openai":
            return OpenAIProvider()
        case "anthropic":
            return AnthropicProvider()
        case _:
            return MockProvider()


def default_llm_config() -> LLMConfig:
    settings = get_settings()
    model_for = _MODEL_BY_PROVIDER.get(settings.llm_provider, lambda s: s.ollama_model)
    return LLMConfig(
        model=model_for(settings),
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout_seconds=settings.llm_request_timeout_seconds,
        max_retries=settings.llm_max_retries,
        retry_backoff_seconds=settings.llm_retry_backoff_seconds,
    )

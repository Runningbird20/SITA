"""Opportunistic integration test against a real Ollama instance —
[STRETCH] in TODO.md § Phase 6. Skips itself entirely when no Ollama is
reachable, so it never blocks CI or a machine without Ollama installed.
"""

import httpx
import pytest
from pydantic import BaseModel

from app.core.config import get_settings
from app.llm.ollama_provider import OllamaProvider
from app.llm.types import LLMConfig, LLMRequest
from app.models.enums import AnalysisTaskType, AnalysisValidationStatus


def _configured_model_is_pulled() -> bool:
    """Not just "is Ollama reachable" — Ollama can be up with zero models
    pulled, which would otherwise fail this test with a confusing 404
    instead of skipping cleanly.
    """
    settings = get_settings()
    try:
        response = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=1.0)
        response.raise_for_status()
    except httpx.HTTPError:
        return False
    pulled_models = {m["name"] for m in response.json().get("models", [])}
    return settings.ollama_model in pulled_models


pytestmark = pytest.mark.skipif(
    not _configured_model_is_pulled(),
    reason="no reachable Ollama instance with the configured model pulled",
)


class _LiveDiagnosticSchema(BaseModel):
    answer: str


class TestOllamaLiveRoundTrip:
    def test_real_completion_round_trip(self):
        provider = OllamaProvider()
        settings = get_settings()
        config = LLMConfig(
            model=settings.ollama_model,
            timeout_seconds=settings.llm_request_timeout_seconds,
            max_retries=1,
            retry_backoff_seconds=0.5,
        )
        request = LLMRequest(
            task_type=AnalysisTaskType.INCIDENT_SUMMARY,
            prompt=('Respond with exactly this JSON object and nothing else: {"answer": "pong"}'),
            response_schema=_LiveDiagnosticSchema,
            prompt_version="live-test-v1",
        )

        response = provider.generate(request, config)

        assert response.provider == "ollama"
        assert response.latency_ms > 0
        # A real local model may or may not follow the format instruction
        # perfectly — this test asserts the round-trip and metadata are
        # real, not that the model is well-behaved.
        assert response.validation_status in {
            AnalysisValidationStatus.VALID,
            AnalysisValidationStatus.INVALID,
        }
        if response.validation_status == AnalysisValidationStatus.VALID:
            assert response.confidence is not None

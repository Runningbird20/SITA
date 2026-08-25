import pytest
from pydantic import BaseModel

from app.llm.exceptions import LLMProviderError, LLMTimeoutError
from app.llm.mock_provider import MockProvider
from app.llm.types import LLMConfig, LLMRequest, RawCompletion
from app.models.enums import AnalysisTaskType, AnalysisValidationStatus


class _ExampleSchema(BaseModel):
    summary: str


def _request() -> LLMRequest:
    return LLMRequest(
        task_type=AnalysisTaskType.INCIDENT_SUMMARY,
        prompt="test",
        response_schema=_ExampleSchema,
        prompt_version="v1",
    )


def _config(**overrides) -> LLMConfig:
    defaults = {"model": "test-model", "retry_backoff_seconds": 0.0}
    defaults.update(overrides)
    return LLMConfig(**defaults)


class TestMockProviderConstruction:
    def test_rejects_both_responses_and_raises(self):
        with pytest.raises(ValueError, match="either responses or raises"):
            MockProvider(responses=RawCompletion(text="{}"), raises=LLMTimeoutError("x"))


class TestMockProviderResponses:
    def test_no_config_returns_empty_object_by_default(self):
        provider = MockProvider()
        response = provider.generate(_request(), _config())
        assert response.raw_output == "{}"

    def test_single_repeating_response_returned_every_call(self):
        provider = MockProvider(responses=RawCompletion(text='{"summary": "x"}'))
        r1 = provider.generate(_request(), _config())
        r2 = provider.generate(_request(), _config())
        assert r1.parsed_output == {"summary": "x"}
        assert r2.parsed_output == {"summary": "x"}

    def test_queue_is_consumed_in_order(self):
        provider = MockProvider(
            responses=[
                RawCompletion(text='{"summary": "first"}'),
                RawCompletion(text='{"summary": "second"}'),
            ]
        )
        r1 = provider.generate(_request(), _config(max_retries=0))
        r2 = provider.generate(_request(), _config(max_retries=0))
        assert r1.parsed_output == {"summary": "first"}
        assert r2.parsed_output == {"summary": "second"}


class TestMockProviderFailures:
    def test_raises_timeout_error(self):
        provider = MockProvider(raises=LLMTimeoutError("simulated timeout"))
        response = provider.generate(_request(), _config(max_retries=0))
        assert response.validation_status == AnalysisValidationStatus.TIMEOUT
        assert "simulated timeout" in response.error

    def test_raises_provider_error(self):
        provider = MockProvider(raises=LLMProviderError("connection refused"))
        response = provider.generate(_request(), _config(max_retries=0))
        assert response.validation_status == AnalysisValidationStatus.PROVIDER_ERROR

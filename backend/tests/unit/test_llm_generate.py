from pydantic import BaseModel

from app.core.metrics import llm_call_duration_seconds, llm_calls_total
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


class TestRetryBehavior:
    def test_succeeds_on_first_attempt_confidence_full(self):
        provider = MockProvider(responses=RawCompletion(text='{"summary": "ok"}'))
        config = LLMConfig(model="test", max_retries=2, retry_backoff_seconds=0)
        response = provider.generate(_request(), config)
        assert response.validation_status == AnalysisValidationStatus.VALID
        assert response.confidence == 1.0

    def test_invalid_output_is_retried_and_recovers(self):
        provider = MockProvider(
            responses=[RawCompletion(text="not json"), RawCompletion(text='{"summary": "ok"}')]
        )
        config = LLMConfig(model="test", max_retries=2, retry_backoff_seconds=0)
        response = provider.generate(_request(), config)
        assert response.validation_status == AnalysisValidationStatus.VALID
        # succeeded on the 2nd attempt -> one retry consumed -> confidence penalized once
        assert response.confidence == 0.85

    def test_confidence_floors_at_minimum_regardless_of_retry_count(self):
        provider = MockProvider(
            responses=[
                RawCompletion(text="bad"),
                RawCompletion(text="bad"),
                RawCompletion(text="bad"),
                RawCompletion(text="bad"),
                RawCompletion(text='{"summary": "ok"}'),
            ]
        )
        config = LLMConfig(model="test", max_retries=4, retry_backoff_seconds=0)
        response = provider.generate(_request(), config)
        assert response.validation_status == AnalysisValidationStatus.VALID
        assert response.confidence == 0.5

    def test_exhausting_retries_on_invalid_output_returns_invalid(self):
        provider = MockProvider(responses=RawCompletion(text="always bad"))
        config = LLMConfig(model="test", max_retries=2, retry_backoff_seconds=0)
        response = provider.generate(_request(), config)
        assert response.validation_status == AnalysisValidationStatus.INVALID
        assert response.parsed_output is None
        assert response.confidence is None

    def test_exhausting_retries_on_timeout_returns_timeout_status(self):
        provider = MockProvider(raises=LLMTimeoutError("simulated"))
        config = LLMConfig(model="test", max_retries=2, retry_backoff_seconds=0)
        response = provider.generate(_request(), config)
        assert response.validation_status == AnalysisValidationStatus.TIMEOUT

    def test_exhausting_retries_on_provider_error_returns_provider_error_status(self):
        provider = MockProvider(raises=LLMProviderError("simulated"))
        config = LLMConfig(model="test", max_retries=2, retry_backoff_seconds=0)
        response = provider.generate(_request(), config)
        assert response.validation_status == AnalysisValidationStatus.PROVIDER_ERROR

    def test_zero_max_retries_means_exactly_one_attempt(self):
        provider = MockProvider(responses=RawCompletion(text="bad"))
        config = LLMConfig(model="test", max_retries=0, retry_backoff_seconds=0)
        response = provider.generate(_request(), config)
        assert response.validation_status == AnalysisValidationStatus.INVALID


class TestResponseMetadata:
    def test_response_records_provider_model_and_prompt_version(self):
        provider = MockProvider(responses=RawCompletion(text='{"summary": "ok"}'))
        config = LLMConfig(model="llama3.1:8b-instruct-q4_K_M", retry_backoff_seconds=0)
        response = provider.generate(_request(), config)
        assert response.provider == "mock"
        assert response.model == "llama3.1:8b-instruct-q4_K_M"
        assert response.prompt_version == "v1"
        assert response.latency_ms >= 0

    def test_token_counts_pass_through(self):
        provider = MockProvider(
            responses=RawCompletion(
                text='{"summary": "ok"}', prompt_tokens=42, completion_tokens=17
            )
        )
        config = LLMConfig(model="test", retry_backoff_seconds=0)
        response = provider.generate(_request(), config)
        assert response.prompt_tokens == 42
        assert response.completion_tokens == 17

    def test_never_raises_on_any_failure_mode(self):
        for exc in (LLMTimeoutError("x"), LLMProviderError("y")):
            provider = MockProvider(raises=exc)
            config = LLMConfig(model="test", max_retries=1, retry_backoff_seconds=0)
            # Should not raise — the whole point of generate()'s contract.
            response = provider.generate(_request(), config)
            assert response is not None


class TestLLMMetrics:
    def test_successful_call_increments_calls_and_records_duration(self):
        labels = {"provider": "mock", "model": "test-metrics", "task_type": "incident_summary"}
        calls_before = llm_calls_total.labels(**labels, status="valid")._value.get()
        duration_before = llm_call_duration_seconds.labels(**labels)._sum.get()

        provider = MockProvider(responses=RawCompletion(text='{"summary": "ok"}'))
        config = LLMConfig(model="test-metrics", retry_backoff_seconds=0)
        provider.generate(_request(), config)

        assert llm_calls_total.labels(**labels, status="valid")._value.get() == calls_before + 1
        assert llm_call_duration_seconds.labels(**labels)._sum.get() >= duration_before

    def test_each_retry_attempt_is_counted_separately(self):
        labels = {"provider": "mock", "model": "test-retries", "task_type": "incident_summary"}
        invalid_before = llm_calls_total.labels(**labels, status="invalid")._value.get()

        provider = MockProvider(responses=RawCompletion(text="always bad"))
        config = LLMConfig(model="test-retries", max_retries=2, retry_backoff_seconds=0)
        provider.generate(_request(), config)

        # 3 attempts total (1 + 2 retries), all invalid.
        assert llm_calls_total.labels(**labels, status="invalid")._value.get() == (
            invalid_before + 3
        )

"""The LLMProvider abstraction. See DEF.md § Phase 6.

generate() is concrete on this base class — retry/timeout handling,
structured-output validation, confidence derivation, and logging are
identical for every provider, so they live here once. Subclasses implement
only `_complete()`: one unretried call to the underlying model.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import ClassVar

from app.llm.exceptions import LLMProviderError, LLMTimeoutError
from app.llm.types import LLMConfig, LLMRequest, LLMResponse, RawCompletion
from app.llm.validation import validate_structured_output
from app.models.enums import AnalysisValidationStatus

logger = logging.getLogger(__name__)

_MIN_CONFIDENCE = 0.5
_CONFIDENCE_PENALTY_PER_RETRY = 0.15


def _confidence_for_attempt(attempt: int) -> float:
    """attempt is 1-indexed (1 = succeeded on the first try, no retries
    consumed). Never asks the model to self-report confidence — reflects
    only how much the validation process had to fight to get a usable
    answer.
    """
    return max(_MIN_CONFIDENCE, 1.0 - _CONFIDENCE_PENALTY_PER_RETRY * (attempt - 1))


class LLMProvider(ABC):
    name: ClassVar[str]

    def generate(self, request: LLMRequest, config: LLMConfig) -> LLMResponse:
        """Never raises: every failure mode (timeout, connection error,
        invalid output) becomes a returned LLMResponse with
        validation_status reflecting what happened, not an exception a
        caller has to remember to catch.
        """
        total_attempts = config.max_retries + 1
        last_raw_text = ""
        last_error: str | None = None
        last_status = AnalysisValidationStatus.PROVIDER_ERROR
        last_tokens: tuple[int | None, int | None] = (None, None)

        for attempt in range(1, total_attempts + 1):
            start = time.monotonic()
            try:
                completion: RawCompletion = self._complete(request.prompt, config)
            except LLMTimeoutError as exc:
                latency_ms = int((time.monotonic() - start) * 1000)
                last_status, last_error = AnalysisValidationStatus.TIMEOUT, str(exc)
                logger.warning(
                    "LLM call timed out",
                    extra={
                        "provider": self.name,
                        "model": config.model,
                        "task_type": request.task_type.value,
                        "attempt": attempt,
                        "latency_ms": latency_ms,
                    },
                )
                if attempt < total_attempts:
                    time.sleep(config.retry_backoff_seconds)
                    continue
                return self._failure_response(request, config, last_status, last_error, latency_ms)
            except LLMProviderError as exc:
                latency_ms = int((time.monotonic() - start) * 1000)
                last_status, last_error = AnalysisValidationStatus.PROVIDER_ERROR, str(exc)
                logger.warning(
                    "LLM provider call failed",
                    extra={
                        "provider": self.name,
                        "model": config.model,
                        "task_type": request.task_type.value,
                        "attempt": attempt,
                        "latency_ms": latency_ms,
                    },
                )
                if attempt < total_attempts:
                    time.sleep(config.retry_backoff_seconds)
                    continue
                return self._failure_response(request, config, last_status, last_error, latency_ms)

            latency_ms = int((time.monotonic() - start) * 1000)
            last_raw_text = completion.text
            last_tokens = (completion.prompt_tokens, completion.completion_tokens)
            parsed, status, error = validate_structured_output(
                completion.text, request.response_schema
            )

            logger.info(
                "LLM call completed",
                extra={
                    "provider": self.name,
                    "model": config.model,
                    "task_type": request.task_type.value,
                    "prompt_version": request.prompt_version,
                    "attempt": attempt,
                    "latency_ms": latency_ms,
                    "validation_status": status.value,
                },
            )

            if status == AnalysisValidationStatus.VALID:
                return LLMResponse(
                    provider=self.name,
                    model=config.model,
                    prompt_version=request.prompt_version,
                    raw_output=completion.text,
                    parsed_output=parsed,
                    validation_status=status,
                    confidence=_confidence_for_attempt(attempt),
                    latency_ms=latency_ms,
                    prompt_tokens=completion.prompt_tokens,
                    completion_tokens=completion.completion_tokens,
                    error=None,
                )

            last_status, last_error = status, error
            if attempt < total_attempts:
                time.sleep(config.retry_backoff_seconds)
                continue

        return LLMResponse(
            provider=self.name,
            model=config.model,
            prompt_version=request.prompt_version,
            raw_output=last_raw_text,
            parsed_output=None,
            validation_status=last_status,
            confidence=None,
            latency_ms=latency_ms,
            prompt_tokens=last_tokens[0],
            completion_tokens=last_tokens[1],
            error=last_error,
        )

    def _failure_response(
        self,
        request: LLMRequest,
        config: LLMConfig,
        status: AnalysisValidationStatus,
        error: str | None,
        latency_ms: int,
    ) -> LLMResponse:
        return LLMResponse(
            provider=self.name,
            model=config.model,
            prompt_version=request.prompt_version,
            raw_output="",
            parsed_output=None,
            validation_status=status,
            confidence=None,
            latency_ms=latency_ms,
            error=error,
        )

    @abstractmethod
    def _complete(self, prompt: str, config: LLMConfig) -> RawCompletion:
        """One unretried call to the underlying model. Raise
        LLMTimeoutError or LLMProviderError on failure — generate() above
        decides whether to retry, not the subclass.
        """

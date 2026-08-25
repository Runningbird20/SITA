"""Request/response types for the LLM provider abstraction. See DEF.md § Phase 6."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.models.enums import AnalysisTaskType, AnalysisValidationStatus

if TYPE_CHECKING:
    from pydantic import BaseModel


@dataclass
class LLMConfig:
    model: str
    temperature: float = 0.2
    max_tokens: int = 1024
    timeout_seconds: float = 30.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.2


@dataclass
class LLMRequest:
    task_type: AnalysisTaskType
    prompt: str
    response_schema: type["BaseModel"]
    prompt_version: str


@dataclass
class RawCompletion:
    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass
class LLMResponse:
    provider: str
    model: str
    prompt_version: str
    raw_output: str
    parsed_output: dict | None
    validation_status: AnalysisValidationStatus
    confidence: float | None
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    error: str | None = None

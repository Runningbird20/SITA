"""A deterministic double for LLMProvider — zero network I/O, ever. Goes
through the exact same generate() retry/validation/logging path as
OllamaProvider; this class only stands in for _complete(). See DEF.md § Phase 6.
"""

from collections import deque

from app.llm.base import LLMProvider
from app.llm.types import LLMConfig, RawCompletion


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(
        self,
        responses: RawCompletion | list[RawCompletion] | None = None,
        raises: Exception | None = None,
    ):
        """`responses`: a single canned RawCompletion (returned every call)
        or a queue of them (popped one per call, useful for testing
        multi-attempt retry sequences — e.g. an invalid response followed
        by a valid one). `raises`: an LLMTimeoutError or LLMProviderError
        to raise on every call instead, for testing failure paths.
        """
        if raises is not None and responses is not None:
            raise ValueError("MockProvider takes either responses or raises, not both")
        self._raises = raises

        if isinstance(responses, list):
            self._queue: deque[RawCompletion] = deque(responses)
            self._repeating: RawCompletion | None = None
        elif isinstance(responses, RawCompletion):
            self._queue = deque()
            self._repeating = responses
        else:
            self._queue = deque()
            self._repeating = None

    def _complete(self, prompt: str, config: LLMConfig) -> RawCompletion:
        if self._raises is not None:
            raise self._raises

        if self._queue:
            return self._queue.popleft()
        if self._repeating is not None:
            return self._repeating
        return RawCompletion(text="{}")

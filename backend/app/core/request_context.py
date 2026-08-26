"""Per-request request ID propagation into every log line. See DEF.md § Phase 13.

A ContextVar rather than an argument threaded through every function: it
lets every logger in the app pick up the current request ID for free (via
RequestIdFilter, attached once in configure_logging()) without every
pipeline function accepting and forwarding a request_id parameter. Unset
(None) outside of an HTTP request — CLI invocations, Alembic, the
evaluation/benchmark harnesses — which is correct, not a gap: those aren't
triggered by a request.
"""

import contextvars
import logging

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return _request_id.get()


def set_request_id(value: str | None) -> contextvars.Token:
    return _request_id.set(value)


def reset_request_id(token: contextvars.Token) -> None:
    _request_id.reset(token)


class RequestIdFilter(logging.Filter):
    """Stamps every LogRecord with the current request ID, so JSON log
    output includes it without every logger.info() call passing it via
    `extra=`.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True

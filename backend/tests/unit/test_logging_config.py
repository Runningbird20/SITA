import logging

import app.core.logging as logging_module
from app.core.config import Settings
from app.core.logging import configure_logging
from app.core.request_context import RequestIdFilter


class TestConfigureLogging:
    def test_idempotent_second_call_is_a_no_op(self, monkeypatch):
        monkeypatch.setattr(logging_module, "_CONFIGURED", True)
        root_handlers_before = list(logging.getLogger().handlers)
        configure_logging()
        assert logging.getLogger().handlers == root_handlers_before

    def test_console_format_uses_plain_formatter_and_attaches_request_id_filter(self, monkeypatch):
        original_handlers = list(logging.getLogger().handlers)
        try:
            monkeypatch.setattr(logging_module, "_CONFIGURED", False)
            monkeypatch.setattr(
                logging_module, "get_settings", lambda: Settings(log_format="console")
            )
            configure_logging()

            handler = logging.getLogger().handlers[0]
            assert isinstance(handler.formatter, logging.Formatter)
            assert any(isinstance(f, RequestIdFilter) for f in handler.filters)
        finally:
            logging.getLogger().handlers = original_handlers

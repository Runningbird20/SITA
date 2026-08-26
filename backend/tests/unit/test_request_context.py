import logging

from app.core.request_context import (
    RequestIdFilter,
    get_request_id,
    reset_request_id,
    set_request_id,
)


class TestRequestIdContextVar:
    def test_defaults_to_none(self):
        assert get_request_id() is None

    def test_set_and_get_roundtrip(self):
        token = set_request_id("abc-123")
        try:
            assert get_request_id() == "abc-123"
        finally:
            reset_request_id(token)
        assert get_request_id() is None

    def test_reset_restores_prior_value_for_nested_scopes(self):
        outer_token = set_request_id("outer")
        inner_token = set_request_id("inner")
        assert get_request_id() == "inner"
        reset_request_id(inner_token)
        assert get_request_id() == "outer"
        reset_request_id(outer_token)
        assert get_request_id() is None


class TestRequestIdFilter:
    def test_stamps_record_with_current_request_id(self):
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "msg", None, None)
        token = set_request_id("req-42")
        try:
            assert RequestIdFilter().filter(record) is True
            assert record.request_id == "req-42"
        finally:
            reset_request_id(token)

    def test_stamps_none_when_unset(self):
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "msg", None, None)
        assert RequestIdFilter().filter(record) is True
        assert record.request_id is None

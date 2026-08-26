"""AnthropicProvider — DEF.md § Phase 6 "Post-roadmap addition". Fully
mocked httpx, never a real network call — a real call to Anthropic would
cost real money, so there is deliberately no opportunistic-live
counterpart to test_llm_ollama_live.py here.
"""

import httpx
import pytest

from app.llm.anthropic_provider import AnthropicProvider
from app.llm.exceptions import LLMProviderError, LLMTimeoutError
from app.llm.types import LLMConfig


def _config() -> LLMConfig:
    return LLMConfig(model="claude-3-5-haiku-20241022", timeout_seconds=5)


class TestAnthropicProviderComplete:
    def test_successful_call_parses_response_and_token_counts(self, monkeypatch):
        def fake_post(url, headers, json, timeout):
            assert url == "https://api.anthropic.com/v1/messages"
            assert headers["x-api-key"] == "test-key"
            assert headers["anthropic-version"] == "2023-06-01"
            assert json["model"] == "claude-3-5-haiku-20241022"
            assert json["messages"] == [{"role": "user", "content": "test prompt"}]
            assert json["max_tokens"] == 1024
            return httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": '{"summary": "ok"}'}],
                    "usage": {"input_tokens": 15, "output_tokens": 7},
                },
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(httpx, "post", fake_post)
        provider = AnthropicProvider(base_url="https://api.anthropic.com", api_key="test-key")
        completion = provider._complete("test prompt", _config())
        assert completion.text == '{"summary": "ok"}'
        assert completion.prompt_tokens == 15
        assert completion.completion_tokens == 7

    def test_multiple_text_blocks_are_concatenated(self, monkeypatch):
        def fake_post(url, headers, json, timeout):
            return httpx.Response(
                200,
                json={
                    "content": [
                        {"type": "text", "text": "part one "},
                        {"type": "text", "text": "part two"},
                    ],
                    "usage": {},
                },
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(httpx, "post", fake_post)
        provider = AnthropicProvider(base_url="https://api.anthropic.com", api_key="test-key")
        completion = provider._complete("test prompt", _config())
        assert completion.text == "part one part two"

    def test_timeout_is_translated_to_llm_timeout_error(self, monkeypatch):
        def fake_post(url, headers, json, timeout):
            raise httpx.TimeoutException("timed out")

        monkeypatch.setattr(httpx, "post", fake_post)
        provider = AnthropicProvider(base_url="https://api.anthropic.com", api_key="test-key")
        with pytest.raises(LLMTimeoutError):
            provider._complete("test prompt", _config())

    def test_connection_error_is_translated_to_llm_provider_error(self, monkeypatch):
        def fake_post(url, headers, json, timeout):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(httpx, "post", fake_post)
        provider = AnthropicProvider(base_url="https://api.anthropic.com", api_key="test-key")
        with pytest.raises(LLMProviderError):
            provider._complete("test prompt", _config())

    def test_http_error_status_is_translated_to_llm_provider_error(self, monkeypatch):
        def fake_post(url, headers, json, timeout):
            request = httpx.Request("POST", url)
            return httpx.Response(401, json={"error": "invalid api key"}, request=request)

        monkeypatch.setattr(httpx, "post", fake_post)
        provider = AnthropicProvider(base_url="https://api.anthropic.com", api_key="test-key")
        with pytest.raises(LLMProviderError):
            provider._complete("test prompt", _config())

    def test_base_url_and_key_fall_back_to_settings(self):
        provider = AnthropicProvider()
        assert provider._base_url  # non-empty, sourced from Settings.anthropic_base_url
        assert provider._api_key == ""  # Settings.anthropic_api_key default: unset

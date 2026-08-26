"""OpenAIProvider and LMStudioProvider — DEF.md § Phase 6 "Post-roadmap
addition". Fully mocked httpx, never a real network call — unlike Ollama,
a real call to OpenAI would cost real money, so there is deliberately no
opportunistic-live counterpart to test_llm_ollama_live.py here.
"""

import httpx
import pytest

from app.llm.exceptions import LLMProviderError, LLMTimeoutError
from app.llm.openai_provider import LMStudioProvider, OpenAIProvider
from app.llm.types import LLMConfig


def _config() -> LLMConfig:
    return LLMConfig(model="gpt-4o-mini", timeout_seconds=5)


class TestOpenAIProviderComplete:
    def test_successful_call_parses_response_and_token_counts(self, monkeypatch):
        def fake_post(url, headers, json, timeout):
            assert url == "https://api.openai.com/v1/chat/completions"
            assert headers["Authorization"] == "Bearer test-key"
            assert json["model"] == "gpt-4o-mini"
            assert json["messages"] == [{"role": "user", "content": "test prompt"}]
            assert json["response_format"] == {"type": "json_object"}
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": '{"summary": "ok"}'}}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 6},
                },
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(httpx, "post", fake_post)
        provider = OpenAIProvider(base_url="https://api.openai.com/v1", api_key="test-key")
        completion = provider._complete("test prompt", _config())
        assert completion.text == '{"summary": "ok"}'
        assert completion.prompt_tokens == 12
        assert completion.completion_tokens == 6

    def test_timeout_is_translated_to_llm_timeout_error(self, monkeypatch):
        def fake_post(url, headers, json, timeout):
            raise httpx.TimeoutException("timed out")

        monkeypatch.setattr(httpx, "post", fake_post)
        provider = OpenAIProvider(base_url="https://api.openai.com/v1", api_key="test-key")
        with pytest.raises(LLMTimeoutError):
            provider._complete("test prompt", _config())

    def test_connection_error_is_translated_to_llm_provider_error(self, monkeypatch):
        def fake_post(url, headers, json, timeout):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(httpx, "post", fake_post)
        provider = OpenAIProvider(base_url="https://api.openai.com/v1", api_key="test-key")
        with pytest.raises(LLMProviderError):
            provider._complete("test prompt", _config())

    def test_http_error_status_is_translated_to_llm_provider_error(self, monkeypatch):
        def fake_post(url, headers, json, timeout):
            request = httpx.Request("POST", url)
            return httpx.Response(401, json={"error": "invalid api key"}, request=request)

        monkeypatch.setattr(httpx, "post", fake_post)
        provider = OpenAIProvider(base_url="https://api.openai.com/v1", api_key="test-key")
        with pytest.raises(LLMProviderError):
            provider._complete("test prompt", _config())

    def test_base_url_and_key_fall_back_to_settings(self):
        provider = OpenAIProvider()
        assert provider._base_url  # non-empty, sourced from Settings.openai_base_url
        assert provider._api_key == ""  # Settings.openai_api_key default: unset


class TestLMStudioProviderReusesOpenAIProviderLogic:
    def test_name_is_lm_studio_not_openai(self):
        assert LMStudioProvider.name == "lm_studio"

    def test_uses_lm_studio_base_url_and_a_placeholder_key(self, monkeypatch):
        captured = {}

        def fake_post(url, headers, json, timeout):
            captured["url"] = url
            captured["headers"] = headers
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "{}"}}], "usage": {}},
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(httpx, "post", fake_post)
        provider = LMStudioProvider(base_url="http://localhost:1234/v1")
        provider._complete("test prompt", _config())

        assert captured["url"] == "http://localhost:1234/v1/chat/completions"
        assert captured["headers"]["Authorization"] == "Bearer lm-studio"

    def test_base_url_falls_back_to_settings(self):
        provider = LMStudioProvider()
        assert provider._base_url  # non-empty, sourced from Settings.lm_studio_base_url

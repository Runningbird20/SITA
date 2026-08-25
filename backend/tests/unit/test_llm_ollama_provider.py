import httpx
import pytest

from app.llm.exceptions import LLMProviderError, LLMTimeoutError
from app.llm.ollama_provider import OllamaProvider
from app.llm.types import LLMConfig


def _config() -> LLMConfig:
    return LLMConfig(model="llama3.1:8b-instruct-q4_K_M", timeout_seconds=5)


class TestOllamaProviderComplete:
    def test_successful_call_parses_response_and_token_counts(self, monkeypatch):
        def fake_post(url, json, timeout):
            assert url == "http://localhost:11434/api/generate"
            assert json["model"] == "llama3.1:8b-instruct-q4_K_M"
            assert json["format"] == "json"
            assert json["stream"] is False
            return httpx.Response(
                200,
                json={"response": '{"summary": "ok"}', "prompt_eval_count": 10, "eval_count": 5},
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(httpx, "post", fake_post)
        provider = OllamaProvider(base_url="http://localhost:11434")
        completion = provider._complete("test prompt", _config())
        assert completion.text == '{"summary": "ok"}'
        assert completion.prompt_tokens == 10
        assert completion.completion_tokens == 5

    def test_timeout_is_translated_to_llm_timeout_error(self, monkeypatch):
        def fake_post(url, json, timeout):
            raise httpx.TimeoutException("timed out")

        monkeypatch.setattr(httpx, "post", fake_post)
        provider = OllamaProvider(base_url="http://localhost:11434")
        with pytest.raises(LLMTimeoutError):
            provider._complete("test prompt", _config())

    def test_connection_error_is_translated_to_llm_provider_error(self, monkeypatch):
        def fake_post(url, json, timeout):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(httpx, "post", fake_post)
        provider = OllamaProvider(base_url="http://localhost:11434")
        with pytest.raises(LLMProviderError):
            provider._complete("test prompt", _config())

    def test_http_error_status_is_translated_to_llm_provider_error(self, monkeypatch):
        def fake_post(url, json, timeout):
            request = httpx.Request("POST", url)
            return httpx.Response(500, json={"error": "model not found"}, request=request)

        monkeypatch.setattr(httpx, "post", fake_post)
        provider = OllamaProvider(base_url="http://localhost:11434")
        with pytest.raises(LLMProviderError):
            provider._complete("test prompt", _config())

    def test_base_url_falls_back_to_settings(self):
        provider = OllamaProvider()
        assert provider._base_url  # non-empty, sourced from Settings.ollama_base_url

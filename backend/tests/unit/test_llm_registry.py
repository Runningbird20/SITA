from app.core.config import Settings, get_settings
from app.llm.mock_provider import MockProvider
from app.llm.ollama_provider import OllamaProvider
from app.llm.registry import default_llm_config, get_llm_provider


class TestGetLLMProvider:
    def test_defaults_to_mock(self, monkeypatch):
        monkeypatch.setattr("app.llm.registry.get_settings", lambda: Settings(llm_provider="mock"))
        assert isinstance(get_llm_provider(), MockProvider)

    def test_ollama_setting_returns_ollama_provider(self, monkeypatch):
        monkeypatch.setattr(
            "app.llm.registry.get_settings", lambda: Settings(llm_provider="ollama")
        )
        assert isinstance(get_llm_provider(), OllamaProvider)

    def test_current_default_settings_use_mock(self):
        # The real, unmodified project default — matches the Definition of
        # Done: the app runs with zero LLM network dependency out of the box.
        assert get_settings().llm_provider == "mock"
        assert isinstance(get_llm_provider(), MockProvider)


class TestDefaultLLMConfig:
    def test_reads_from_settings(self, monkeypatch):
        monkeypatch.setattr(
            "app.llm.registry.get_settings",
            lambda: Settings(
                ollama_model="custom-model",
                llm_temperature=0.7,
                llm_request_timeout_seconds=15.0,
                llm_max_retries=5,
            ),
        )
        config = default_llm_config()
        assert config.model == "custom-model"
        assert config.temperature == 0.7
        assert config.timeout_seconds == 15.0
        assert config.max_retries == 5

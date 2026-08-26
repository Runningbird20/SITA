from app.core.config import Settings, get_settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.mock_provider import MockProvider
from app.llm.ollama_provider import OllamaProvider
from app.llm.openai_provider import LMStudioProvider, OpenAIProvider
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

    def test_lm_studio_setting_returns_lm_studio_provider(self, monkeypatch):
        monkeypatch.setattr(
            "app.llm.registry.get_settings", lambda: Settings(llm_provider="lm_studio")
        )
        assert isinstance(get_llm_provider(), LMStudioProvider)

    def test_openai_setting_returns_openai_provider_not_lm_studio(self, monkeypatch):
        monkeypatch.setattr(
            "app.llm.registry.get_settings", lambda: Settings(llm_provider="openai")
        )
        provider = get_llm_provider()
        assert isinstance(provider, OpenAIProvider)
        assert not isinstance(provider, LMStudioProvider)
        assert provider.name == "openai"

    def test_anthropic_setting_returns_anthropic_provider(self, monkeypatch):
        monkeypatch.setattr(
            "app.llm.registry.get_settings", lambda: Settings(llm_provider="anthropic")
        )
        assert isinstance(get_llm_provider(), AnthropicProvider)

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

    def test_model_is_selected_from_the_active_providers_own_setting(self, monkeypatch):
        # Each provider has its own *_model setting — default_llm_config()
        # must pick the one matching llm_provider, not always ollama_model.
        monkeypatch.setattr(
            "app.llm.registry.get_settings",
            lambda: Settings(
                llm_provider="openai",
                ollama_model="ollama-model",
                openai_model="gpt-4o-mini",
                anthropic_model="claude-3-5-haiku-20241022",
                lm_studio_model="local-model",
            ),
        )
        assert default_llm_config().model == "gpt-4o-mini"

        monkeypatch.setattr(
            "app.llm.registry.get_settings",
            lambda: Settings(llm_provider="anthropic", anthropic_model="claude-3-5-haiku-20241022"),
        )
        assert default_llm_config().model == "claude-3-5-haiku-20241022"

        monkeypatch.setattr(
            "app.llm.registry.get_settings",
            lambda: Settings(llm_provider="lm_studio", lm_studio_model="local-model"),
        )
        assert default_llm_config().model == "local-model"

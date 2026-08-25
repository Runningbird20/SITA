from app.llm import cli
from app.llm.mock_provider import MockProvider
from app.llm.types import LLMConfig, RawCompletion

_FAST_CONFIG = LLMConfig(model="test-model", retry_backoff_seconds=0.0)


class TestLLMCli:
    def test_no_prompt_argument_returns_error(self, capsys):
        exit_code = cli.main([])
        assert exit_code == 1
        assert "Usage" in capsys.readouterr().err

    def test_successful_round_trip_prints_response(self, monkeypatch, capsys):
        monkeypatch.setattr(
            cli,
            "get_llm_provider",
            lambda: MockProvider(responses=RawCompletion(text='{"response": "hello there"}')),
        )
        monkeypatch.setattr(cli, "default_llm_config", lambda: _FAST_CONFIG)
        exit_code = cli.main(["hello"])
        assert exit_code == 0
        output = capsys.readouterr().out
        assert "hello there" in output
        assert "validation_status: valid" in output

    def test_failed_round_trip_returns_nonzero_and_prints_error(self, monkeypatch, capsys):
        monkeypatch.setattr(
            cli,
            "get_llm_provider",
            lambda: MockProvider(responses=RawCompletion(text="not json")),
        )
        monkeypatch.setattr(cli, "default_llm_config", lambda: _FAST_CONFIG)
        exit_code = cli.main(["hello"])
        assert exit_code == 1
        output = capsys.readouterr().out
        assert "validation_status: invalid" in output

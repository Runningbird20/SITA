from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application configuration, sourced from environment variables / .env.

    Every setting used anywhere in the app must be declared here — no reading
    os.environ directly elsewhere, so the full configuration surface stays
    discoverable in one place (and documented in .env.example).
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # General
    app_name: str = "SITA"
    environment: str = "development"
    log_level: str = "INFO"
    log_format: str = "json"  # "json" | "console"

    # API
    api_v1_prefix: str = "/api/v1"
    # Empty = auth disabled (the default — every existing quick-start
    # command and test client calls the API with no Authorization header).
    # Set to require `Authorization: Bearer <token>` on every /api/v1/*
    # route. See DEF.md § Phase 14.
    api_auth_token: str = ""
    rate_limit_general_per_minute: int = 300
    rate_limit_strict_per_minute: int = 30
    max_request_body_bytes: int = 10_000_000
    # Both hostnames for the same dev server: browsers treat localhost and
    # 127.0.0.1 as distinct origins for CORS purposes, and which one a
    # given browser/OS resolves "localhost" to isn't guaranteed (see the
    # IPv6-vs-IPv4 note at the top of docker-compose.yml) — allow both so
    # the dashboard doesn't silently fail depending on which URL was opened.
    cors_allow_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Database — SQLAlchemy dialect determines Postgres vs SQLite; both are
    # supported through this single URL with no code branching elsewhere.
    database_url: str = "sqlite:///./sita.db"

    # LLM provider — "mock" (default, zero network) | "ollama" | "lm_studio"
    # (both fully local, no key) | "openai" | "anthropic" (bring-your-own-key,
    # a deliberate exception to "no paid APIs" made at explicit user request —
    # see DEF.md § Phase 6 "Post-roadmap addition"). Retry/timeout/temperature
    # settings below apply to whichever provider is selected.
    llm_provider: str = "mock"
    llm_request_timeout_seconds: float = 30.0
    llm_max_retries: int = 2
    llm_retry_backoff_seconds: float = 0.2
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1024

    # Ollama (fully local, no key). qwen2.5:0.5b is the default specifically
    # because it's small (~400MB) and fast enough to pull and run on modest
    # hardware for a zero-friction quick-start — not because it's the
    # recommended model for real use. For actual triage quality, switch to
    # a 7-8B instruct model (see README's "Enabling real AI triage" for
    # hardware guidance) — see DEF.md § Phase 6 "Recommended local model".
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:0.5b"

    # LM Studio (fully local, no key — its server speaks the same
    # OpenAI-compatible protocol OpenAIProvider already implements).
    # lm_studio_model must match whatever model is currently loaded in LM
    # Studio; there's no sensible universal default.
    lm_studio_base_url: str = "http://localhost:1234/v1"
    lm_studio_model: str = ""

    # OpenAI (bring your own key — empty by default, never required)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    # Anthropic (bring your own key — empty by default, never required)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-20241022"
    anthropic_base_url: str = "https://api.anthropic.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()

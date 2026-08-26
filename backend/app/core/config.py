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
    # Auth is opt-in by DB state, not a config flag: zero `User` rows =
    # disabled (every existing quick-start command and test client calls
    # the API with no Authorization header), non-zero = every /api/v1/*
    # route requires a valid per-user `Authorization: Bearer <token>`
    # issued by `POST /auth/login`. See DEF.md § Phase 14, "Multi-user /
    # RBAC (post-roadmap)" — replaces the single-shared-token model
    # (`api_auth_token`) that predated named users. How long a login
    # session stays valid before requiring a fresh `POST /auth/login`.
    auth_token_expiry_days: int = 7
    rate_limit_general_per_minute: int = 300
    rate_limit_strict_per_minute: int = 30
    max_request_body_bytes: int = 10_000_000
    # Empty (default) = rate limiting stays in-process/single-worker
    # (documented limitation, Phase 13/14). Set to a real Redis URL (the
    # docker-compose services do) to make rate limiting correct across
    # multiple uvicorn workers — see DEF.md § Phase 14, "Multi-process
    # rate limiting (post-roadmap)". Not required for the zero-friction
    # native/SQLite dev path, which never runs more than one worker anyway.
    redis_url: str = ""
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

    # Ollama (fully local, no key). CyberCrew/notmythos-8b is the default —
    # an 8B-class instruct model, replacing this project's earlier
    # quick-start-sized default (see DEF.md § Phase 6 "Recommended local
    # model" for the history). Requires a real multi-gigabyte pull and
    # meaningfully more RAM than a small model — see README's "Enabling
    # real AI triage" for hardware guidance.
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "CyberCrew/notmythos-8b"
    # Ollama's own default (1.1) is often too weak to stop a small model
    # from looping on the same list item in structured JSON output; raised
    # here as a mitigation. Ollama-specific — not part of LLMConfig, since
    # no other provider's API exposes this exact parameter.
    ollama_repeat_penalty: float = 1.3

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

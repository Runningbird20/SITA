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
    cors_allow_origins: list[str] = ["http://localhost:5173"]

    # Database — SQLAlchemy dialect determines Postgres vs SQLite; both are
    # supported through this single URL with no code branching elsewhere.
    database_url: str = "sqlite:///./sita.db"

    # Local LLM (Ollama)
    llm_provider: str = "mock"  # "ollama" | "mock"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b-instruct-q4_K_M"
    llm_request_timeout_seconds: float = 30.0
    llm_max_retries: int = 2
    llm_temperature: float = 0.2


@lru_cache
def get_settings() -> Settings:
    return Settings()

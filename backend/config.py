"""Application configuration loaded from environment variables / `.env`."""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    APP_NAME: str = "Automated Book Generation System"
    APP_VERSION: str = "2.0.0"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "*"  # comma-separated list
    EXPORT_DIR: Path = PROJECT_ROOT / "exports"

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/postgres"

    # LLM
    # auto   -> OpenAI if a key is set, otherwise Gemini (falls back to the other on failure)
    # mock   -> deterministic offline generator, useful for demos and tests
    LLM_PROVIDER: Literal["auto", "openai", "gemini", "mock"] = "auto"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    LLM_TIMEOUT_SECONDS: float = 300.0

    # Book length. Long chapters are written section by section so each LLM call stays
    # well within output limits: sections = ceil(pages * WORDS_PER_PAGE / SECTION_WORDS).
    DEFAULT_CHAPTERS: int = 10
    DEFAULT_PAGES_PER_CHAPTER: int = 20
    WORDS_PER_PAGE: int = 500  # measured in Word for the compiled .docx layout (Georgia 11.5pt, 1.25 spacing)
    SECTION_WORDS: int = 1100
    MAX_CONCURRENT_JOBS: int = 2

    # Notifications
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    NOTIFY_EMAIL_TO: str = ""  # defaults to SMTP_USER
    TEAMS_WEBHOOK_URL: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

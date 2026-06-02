"""Типизированные настройки из окружения (pydantic-settings)."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Единый источник конфигурации. Читается из .env и переменных окружения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LiteLLM прокси ---
    litellm_base_url: str = Field(default="http://litellm:4000/v1")
    litellm_master_key: str = Field(default="sk-litellm-change-me")

    # --- Векторное хранилище / embeddings ---
    qdrant_url: str = Field(default="http://qdrant:6333")
    tei_url: str = Field(default="http://embeddings:80")

    # --- Веб-поиск (SearXNG, self-hosted) ---
    searxng_url: str = Field(default="http://searxng:8080")

    # --- Telegram (Этап 5) ---
    telegram_bot_token: str = Field(default="")
    telegram_allowed_users: str = Field(default="")

    # --- Nextcloud (Этап 3) ---
    nextcloud_url: str = Field(default="")
    nextcloud_user: str = Field(default="")
    nextcloud_app_password: str = Field(default="")

    # --- Gitea (Этап 6) ---
    gitea_url: str = Field(default="")
    gitea_token: str = Field(default="")

    @property
    def allowed_user_ids(self) -> set[int]:
        """Whitelist Telegram user_id из строки '123,456'."""
        raw = self.telegram_allowed_users.strip()
        if not raw:
            return set()
        return {int(x) for x in raw.split(",") if x.strip()}


settings = Settings()

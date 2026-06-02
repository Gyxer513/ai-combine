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

    # --- Векторное хранилище / embeddings (через API, без локального TEI) ---
    qdrant_url: str = Field(default="http://qdrant:6333")
    embed_model: str = Field(default="embed")  # имя модели в LiteLLM (text-embedding-v4)
    embed_dim: int = Field(default=1024)

    # --- RAG ---
    rag_top_k: int = Field(default=5)
    rag_chunk_tokens: int = Field(default=512)
    rag_chunk_overlap: int = Field(default=64)
    # Notes: какие категории в какой namespace (CSV "Категория:namespace").
    # Несопоставленные категории падают в rag_notes_default_ns.
    rag_notes_category_map: str = Field(default="")
    rag_notes_default_ns: str = Field(default="personal")
    # WebDAV: какие папки в какой namespace (CSV "/путь:namespace").
    rag_webdav_folders: str = Field(default="")

    # --- Веб-поиск (SearXNG, self-hosted) ---
    searxng_url: str = Field(default="http://searxng:8080")

    # --- Telegram (Этап 5) ---
    telegram_bot_token: str = Field(default="")
    telegram_allowed_users: str = Field(default="")
    # Куда бот ходит за ответами агентов (в docker — имя сервиса).
    orchestrator_url: str = Field(default="http://orchestrator:8000")

    # --- Nextcloud (Этап 3) ---
    nextcloud_url: str = Field(default="")
    nextcloud_user: str = Field(default="")
    nextcloud_app_password: str = Field(default="")

    # --- Gitea (Этап 6) ---
    gitea_url: str = Field(default="")
    gitea_token: str = Field(default="")

    @property
    def notes_category_map(self) -> dict[str, str]:
        """'AI Projects:personal, Security:security' -> {'AI Projects': 'personal', ...}."""
        out: dict[str, str] = {}
        for pair in self.rag_notes_category_map.split(","):
            cat, _, ns = pair.partition(":")
            if cat.strip() and ns.strip():
                out[cat.strip()] = ns.strip()
        return out

    @property
    def webdav_folders(self) -> list[tuple[str, str]]:
        """'/Knowledge/Security:security' -> [('/Knowledge/Security', 'security'), ...]."""
        out: list[tuple[str, str]] = []
        for pair in self.rag_webdav_folders.split(","):
            path, _, ns = pair.rpartition(":")
            if path.strip() and ns.strip():
                out.append((path.strip(), ns.strip()))
        return out

    @property
    def allowed_user_ids(self) -> set[int]:
        """Whitelist Telegram user_id из строки '123,456'.

        Нечисловые значения (например @username) игнорируются — нужен числовой
        id (см. @userinfobot). Если в итоге пусто — bootstrap-режим (пускает всех).
        """
        ids: set[int] = set()
        for token in self.telegram_allowed_users.split(","):
            token = token.strip()
            if token.isdigit():
                ids.add(int(token))
        return ids


settings = Settings()

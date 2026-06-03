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

    # --- Персистентность (SQLite) ---
    # Файл переживает рестарт: история диалогов, заметки, метрики. ":memory:" в тестах.
    db_path: str = Field(default="data/ai_combine.db")

    # --- Векторное хранилище / embeddings (через API, без локального TEI) ---
    qdrant_url: str = Field(default="http://qdrant:6333")
    embed_model: str = Field(default="embed")  # имя модели в LiteLLM (text-embedding-v4)
    embed_dim: int = Field(default=1024)

    # --- История диалога ---
    # Токен-бюджет истории перед запросом к модели (instructions считаются отдельно).
    # Сверх него ранние сообщения сворачиваются (см. agents/history.py).
    history_max_tokens: int = Field(default=12000)

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
    # Интервал автоиндексации в минутах: >0 — индексатор работает циклом, 0 — один проход.
    rag_index_interval_min: int = Field(default=0)

    # --- Sandbox (Этап 6: изолированное исполнение команд) ---
    # Оркестратор НЕ имеет docker.sock — он ходит в sandbox-broker по HTTP.
    # docker.sock есть только у брокера; параметры ниже читает брокер.
    broker_url: str = Field(default="http://sandbox-broker:9000")
    sandbox_image: str = Field(default="ai-combine/sandbox:latest")
    sandbox_mem: str = Field(default="512m")
    sandbox_cpus: float = Field(default=1.0)
    sandbox_pids: int = Field(default=256)
    sandbox_timeout_sec: int = Field(default=60)
    sandbox_output_limit: int = Field(default=8000)  # символов вывода в ответ модели

    # --- Веб-поиск (SearXNG, self-hosted) ---
    searxng_url: str = Field(default="http://searxng:8080")

    # --- Telegram (Этап 5) ---
    # Один бот на агента: каждый бот жёстко привязан к агенту по своему токену.
    # telegram_bot_token (общий) → Колобок по умолчанию (обратная совместимость);
    # отдельные боты Кощея/Левши создаются в @BotFather, токены — ниже.
    telegram_bot_token: str = Field(default="")
    telegram_bot_token_kolobok: str = Field(default="")
    telegram_bot_token_koschei: str = Field(default="")
    telegram_bot_token_levsha: str = Field(default="")
    telegram_allowed_users: str = Field(default="")
    # Fail-closed: при пустом whitelist по умолчанию НИКОГО не пускаем (id отказанных
    # пишутся в лог — узнать свой и добавить). Открытый bootstrap-режим (пускать
    # всех при пустом списке) — только явным TELEGRAM_ALLOW_BOOTSTRAP=true для дев.
    telegram_allow_bootstrap: bool = Field(default=False)
    # Куда бот ходит за ответами агентов (в docker — имя сервиса).
    orchestrator_url: str = Field(default="http://orchestrator:8000")
    # Сколько бот ждёт ответ агента (секунд). Кощей с серией сканов может работать
    # несколько минут — короткий таймаут даёт ложное «оркестратор недоступен».
    telegram_reply_timeout_sec: int = Field(default=600)

    # --- Nextcloud (Этап 3) ---
    nextcloud_url: str = Field(default="")
    nextcloud_user: str = Field(default="")
    nextcloud_app_password: str = Field(default="")

    # --- Deck-worker (автономия): задачи из Nextcloud Deck ---
    deck_board: str = Field(default="Задачи AI Combine")
    deck_todo_stack: str = Field(default="To Do")
    deck_doing_stack: str = Field(default="In Progress")
    deck_done_stack: str = Field(default="Done")
    # Метка карточки -> агент (CSV "label:agent"). Без метки -> deck_default_agent.
    deck_label_agent_map: str = Field(default="sec:koschei,code:levsha,ask:kolobok")
    deck_default_agent: str = Field(default="kolobok")
    # Интервал опроса доски в минутах: >0 — цикл, 0 — один проход.
    deck_poll_interval_min: int = Field(default=0)

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
    def deck_label_agents(self) -> dict[str, str]:
        """'sec:koschei,code:levsha' -> {'sec': 'koschei', ...} (метка в нижнем регистре)."""
        out: dict[str, str] = {}
        for pair in self.deck_label_agent_map.split(","):
            label, _, agent = pair.partition(":")
            if label.strip() and agent.strip():
                out[label.strip().lower()] = agent.strip()
        return out

    @property
    def agent_bot_tokens(self) -> dict[str, str]:
        """{agent_name: bot_token} для агентов с заданным токеном.

        Колобок берёт telegram_bot_token_kolobok или общий telegram_bot_token.
        Поллятся только агенты с непустым токеном — можно поднять и одного бота.
        """
        out: dict[str, str] = {}
        kolobok = self.telegram_bot_token_kolobok or self.telegram_bot_token
        if kolobok:
            out["kolobok"] = kolobok
        if self.telegram_bot_token_koschei:
            out["koschei"] = self.telegram_bot_token_koschei
        if self.telegram_bot_token_levsha:
            out["levsha"] = self.telegram_bot_token_levsha
        return out

    @property
    def allowed_user_ids(self) -> set[int]:
        """Whitelist Telegram user_id из строки '123,456'.

        Нечисловые значения (например @username) игнорируются — нужен числовой
        id (см. @userinfobot). Пустой результат -> fail-closed (никого), если не
        включён telegram_allow_bootstrap.
        """
        ids: set[int] = set()
        for token in self.telegram_allowed_users.split(","):
            token = token.strip()
            if token.isdigit():
                ids.add(int(token))
        return ids


settings = Settings()

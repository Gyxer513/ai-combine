"""Память агентов на SQLite (переживает рестарт).

Два вида памяти, оба по `conversation_id`:

* **История диалога** — список `ModelMessage` Pydantic AI (сериализуется через
  `ModelMessagesTypeAdapter` в JSON-колонку), чтобы /chat был многоходовым.
* **Scratchpad** — key/value заметки, которые агент сохраняет и читает
  инструментами в рамках разговора.

Раньше было in-memory и сбрасывалось при перезапуске; теперь — таблицы в общей
SQLite-БД (см. persistence.Database). Интерфейс прежний.
"""

from __future__ import annotations

import time

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from ..persistence import Database


class ConversationStore:
    """История сообщений и scratchpad-заметки в SQLite."""

    def __init__(self, db: Database, *, max_messages: int = 100) -> None:
        self._db = db
        self._max_messages = max_messages

    # --- история диалога ---

    def history(self, conversation_id: str) -> list[ModelMessage]:
        """Сообщения разговора (пустой список для нового)."""
        row = self._db.query_one(
            "SELECT messages FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        )
        if row is None:
            return []
        return list(ModelMessagesTypeAdapter.validate_json(row["messages"]))

    def extend_history(self, conversation_id: str, messages: list[ModelMessage]) -> None:
        """Дописать новые сообщения, удержав хвост в пределах `max_messages`."""
        if not messages:
            return
        combined = self.history(conversation_id) + list(messages)
        if len(combined) > self._max_messages:
            combined = combined[-self._max_messages :]
        blob = ModelMessagesTypeAdapter.dump_json(combined).decode("utf-8")
        self._db.execute(
            "INSERT INTO conversations (conversation_id, messages, msg_count, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(conversation_id) DO UPDATE SET "
            "messages = excluded.messages, msg_count = excluded.msg_count, "
            "updated_at = excluded.updated_at",
            (conversation_id, blob, len(combined), time.time()),
        )

    def clear(self, conversation_id: str) -> None:
        """Забыть историю и заметки конкретного разговора."""
        self._db.execute(
            "DELETE FROM conversations WHERE conversation_id = ?", (conversation_id,)
        )
        self._db.execute("DELETE FROM notes WHERE conversation_id = ?", (conversation_id,))

    # --- scratchpad ---

    def save_note(self, conversation_id: str, key: str, value: str) -> None:
        self._db.execute(
            "INSERT INTO notes (conversation_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(conversation_id, key) DO UPDATE SET value = excluded.value",
            (conversation_id, key, value),
        )

    def get_note(self, conversation_id: str, key: str) -> str | None:
        row = self._db.query_one(
            "SELECT value FROM notes WHERE conversation_id = ? AND key = ?",
            (conversation_id, key),
        )
        return row["value"] if row else None

    def all_notes(self, conversation_id: str) -> dict[str, str]:
        rows = self._db.query_all(
            "SELECT key, value FROM notes WHERE conversation_id = ?", (conversation_id,)
        )
        return {r["key"]: r["value"] for r in rows}

    # --- статистика (для дашборда) ---

    def stats(self) -> tuple[int, int]:
        """(число активных разговоров, суммарное число сообщений)."""
        row = self._db.query_one(
            "SELECT COUNT(*) AS c, COALESCE(SUM(msg_count), 0) AS m FROM conversations"
        )
        return (row["c"], row["m"]) if row else (0, 0)

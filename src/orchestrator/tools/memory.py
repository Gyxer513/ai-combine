"""Agent memory on SQLite (survives restarts).

Two kinds of memory, both keyed by `conversation_id`:

* **Conversation history** — a list of Pydantic AI `ModelMessage` (serialized via
  `ModelMessagesTypeAdapter` into a JSON column) so that /chat is multi-turn.
* **Scratchpad** — key/value notes that the agent saves and reads with tools within
  a conversation.

It used to be in-memory and was lost on restart; now these are tables in the shared
SQLite DB (see persistence.Database). The interface is unchanged.
"""

from __future__ import annotations

import time

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from ..persistence import Database


class ConversationStore:
    """Message history and scratchpad notes in SQLite."""

    def __init__(self, db: Database, *, max_messages: int = 100) -> None:
        self._db = db
        self._max_messages = max_messages

    # --- conversation history ---

    def history(self, conversation_id: str) -> list[ModelMessage]:
        """Messages of the conversation (empty list for a new one)."""
        row = self._db.query_one(
            "SELECT messages FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        )
        if row is None:
            return []
        return list(ModelMessagesTypeAdapter.validate_json(row["messages"]))

    def extend_history(self, conversation_id: str, messages: list[ModelMessage]) -> None:
        """Append new messages, keeping the tail within `max_messages`."""
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
        """Forget the history and notes of a specific conversation."""
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

    # --- statistics (for the dashboard) ---

    def stats(self) -> tuple[int, int]:
        """(number of active conversations, total number of messages)."""
        row = self._db.query_one(
            "SELECT COUNT(*) AS c, COALESCE(SUM(msg_count), 0) AS m FROM conversations"
        )
        return (row["c"], row["m"]) if row else (0, 0)

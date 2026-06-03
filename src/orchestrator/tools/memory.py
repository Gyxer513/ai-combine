"""Простая память агентов (Этап 2).

Два вида памяти, оба завязаны на `conversation_id`:

* **История диалога** — список `ModelMessage` Pydantic AI, чтобы /chat был
  многоходовым (агент видит предыдущие реплики).
* **Scratchpad** — key/value заметки, которые агент может сам сохранять и читать
  инструментами в рамках разговора.

Хранилище in-memory на процесс. На будущих этапах заменяется на персистентное
(Qdrant summary / Redis), интерфейс остаётся прежним.
"""

from __future__ import annotations

from collections import defaultdict

from pydantic_ai.messages import ModelMessage


class ConversationStore:
    """In-memory история сообщений и scratchpad-заметки по разговорам."""

    def __init__(self, *, max_messages: int = 100) -> None:
        self._history: dict[str, list[ModelMessage]] = defaultdict(list)
        self._notes: dict[str, dict[str, str]] = defaultdict(dict)
        self._max_messages = max_messages

    # --- история диалога ---

    def history(self, conversation_id: str) -> list[ModelMessage]:
        """Сообщения разговора (пустой список для нового)."""
        return list(self._history[conversation_id])

    def extend_history(self, conversation_id: str, messages: list[ModelMessage]) -> None:
        """Дописать новые сообщения, удержав хвост в пределах `max_messages`."""
        bucket = self._history[conversation_id]
        bucket.extend(messages)
        if len(bucket) > self._max_messages:
            del bucket[: len(bucket) - self._max_messages]

    def clear(self, conversation_id: str) -> None:
        """Забыть историю и заметки конкретного разговора."""
        self._history.pop(conversation_id, None)
        self._notes.pop(conversation_id, None)

    # --- scratchpad ---

    def save_note(self, conversation_id: str, key: str, value: str) -> None:
        self._notes[conversation_id][key] = value

    def get_note(self, conversation_id: str, key: str) -> str | None:
        return self._notes[conversation_id].get(key)

    def all_notes(self, conversation_id: str) -> dict[str, str]:
        return dict(self._notes[conversation_id])

    # --- статистика (для дашборда) ---

    def stats(self) -> tuple[int, int]:
        """(число активных разговоров, суммарное число сообщений в памяти)."""
        return len(self._history), sum(len(b) for b in self._history.values())

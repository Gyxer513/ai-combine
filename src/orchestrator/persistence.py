"""Persistent storage on SQLite.

A single DB file (`db_path`, default `data/ai_combine.db`) survives restarts:
conversation history, scratchpad notes, and metric counters. Previously everything was
in-memory and reset whenever the orchestrator restarted.

`Database` is a thin wrapper over `sqlite3`: one connection (WAL,
`check_same_thread=False`) under a shared `Lock`. The load is personal and low, so
synchronous calls from async handlers are enough — SQLite operations are submillisecond.
The specific tables are served by `ConversationStore` and `Metrics`.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

from .config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    messages        TEXT NOT NULL,
    msg_count       INTEGER NOT NULL DEFAULT 0,
    updated_at      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
    conversation_id TEXT NOT NULL,
    key             TEXT NOT NULL,
    value           TEXT NOT NULL,
    PRIMARY KEY (conversation_id, key)
);
CREATE TABLE IF NOT EXISTS metrics (
    agent         TEXT PRIMARY KEY,
    requests      INTEGER NOT NULL DEFAULT 0,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    last_used     REAL
);
"""


class Database:
    """A SQLite connection with schema and thread-safe writes."""

    def __init__(self, path: str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def execute(self, sql: str, params: Iterable = ()) -> None:
        """Write (INSERT/UPDATE/DELETE) with a commit."""
        with self._lock:
            self._conn.execute(sql, tuple(params))
            self._conn.commit()

    def query_one(self, sql: str, params: Iterable = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchone()

    def query_all(self, sql: str, params: Iterable = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchall()

    def close(self) -> None:
        with self._lock:
            self._conn.close()


@lru_cache(maxsize=1)
def shared_db() -> Database:
    """Process-wide orchestrator database."""
    return Database(settings.db_path)

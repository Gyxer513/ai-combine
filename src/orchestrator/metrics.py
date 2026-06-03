"""Метрики использования агентов (персистентные, для дашборда).

Счётчики (запросы, токены, last_used) хранятся в SQLite и накапливаются между
рестартами. `uptime` — время жизни текущего процесса (in-memory): он отвечает на
вопрос «жив ли сейчас», тогда как счётчики — кумулятивная статистика.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache

from .persistence import Database, shared_db


@dataclass
class AgentMetric:
    """Счётчики одного агента."""

    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    last_used: float | None = None


class Metrics:
    """Счётчики по агентам в SQLite + время старта процесса."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._started = time.time()

    def record(self, agent: str, input_tokens: int, output_tokens: int) -> None:
        """Учесть один запрос к агенту."""
        self._db.execute(
            "INSERT INTO metrics (agent, requests, input_tokens, output_tokens, last_used) "
            "VALUES (?, 1, ?, ?, ?) "
            "ON CONFLICT(agent) DO UPDATE SET "
            "requests = requests + 1, "
            "input_tokens = input_tokens + excluded.input_tokens, "
            "output_tokens = output_tokens + excluded.output_tokens, "
            "last_used = excluded.last_used",
            (agent, max(0, int(input_tokens or 0)), max(0, int(output_tokens or 0)), time.time()),
        )

    def for_agent(self, agent: str) -> AgentMetric:
        row = self._db.query_one(
            "SELECT requests, input_tokens, output_tokens, last_used FROM metrics WHERE agent = ?",
            (agent,),
        )
        if row is None:
            return AgentMetric()
        return AgentMetric(
            requests=row["requests"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            last_used=row["last_used"],
        )

    def uptime_sec(self) -> int:
        return int(time.time() - self._started)


@lru_cache(maxsize=1)
def shared_metrics() -> Metrics:
    """Единый на процесс набор метрик (поверх общей БД)."""
    return Metrics(shared_db())

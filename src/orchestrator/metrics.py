"""Agent usage metrics (persistent, for the dashboard).

Counters (requests, tokens, last_used) are stored in SQLite and accumulate across
restarts. `uptime` is the current process's lifetime (in-memory): it answers
"is it alive right now", whereas the counters are cumulative statistics.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache

from .persistence import Database, shared_db


@dataclass
class AgentMetric:
    """Counters for a single agent."""

    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    last_used: float | None = None


class Metrics:
    """Per-agent counters in SQLite + the process start time."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._started = time.time()

    def record(self, agent: str, input_tokens: int, output_tokens: int) -> None:
        """Record a single request to an agent."""
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
    """Process-wide metrics set (on top of the shared DB)."""
    return Metrics(shared_db())

"""Лёгкие in-memory метрики использования агентов (для дашборда).

Считаются с момента старта процесса и сбрасываются при рестарте — для личного
дашборда «что происходило с запуска» этого достаточно. Персист (если понадобится)
добавим вместе с состоянием по conversation_id.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass
class AgentMetric:
    """Счётчики одного агента."""

    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    last_used: float | None = None


@dataclass
class Metrics:
    """Счётчики по агентам + время старта."""

    started_at: float = field(default_factory=time.time)
    agents: dict[str, AgentMetric] = field(default_factory=dict)

    def record(self, agent: str, input_tokens: int, output_tokens: int) -> None:
        """Учесть один запрос к агенту."""
        m = self.agents.setdefault(agent, AgentMetric())
        m.requests += 1
        m.input_tokens += max(0, int(input_tokens or 0))
        m.output_tokens += max(0, int(output_tokens or 0))
        m.last_used = time.time()

    def uptime_sec(self) -> int:
        return int(time.time() - self.started_at)

    def for_agent(self, agent: str) -> AgentMetric:
        return self.agents.get(agent, AgentMetric())


@lru_cache(maxsize=1)
def shared_metrics() -> Metrics:
    """Единый на процесс набор метрик."""
    return Metrics()

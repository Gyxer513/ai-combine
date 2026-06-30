"""🧭 Planner — Orchestrator Agent.

Принимает ТЗ проекта и режет его на дочерние задачи для остальных агентов
(recon / coder / assistant), раскладывая их карточками на Deck-доску задач — там
их подхватывает deck-worker. Планирование требует сильного ризонинга, поэтому
основная модель `qwen-max`, резерв `qwen-plus`. Чувствительность INTERNAL
(в ТЗ может быть приватный контекст проекта).
"""

from __future__ import annotations

from pydantic_ai import Agent

from ..tools.common import register_common_tools
from ..tools.deck import register_planner_tool
from ..tools.rag import register_rag_tool
from .base import (
    AgentDeps,
    DataSensitivity,
    build_model,
    history_capabilities,
    load_prompt,
)

NAME = "planner"
TITLE = "🧭 Planner"
SENSITIVITY = DataSensitivity.INTERNAL

# Декомпозиция = ризонинг: qwen-max основная, резерв qwen-plus.
MODELS = ["qwen-max", "qwen-plus"]

agent = Agent(
    build_model(MODELS),
    deps_type=AgentDeps,
    instructions=load_prompt(NAME),  # см. пояснение в assistant.py
    name=NAME,
    capabilities=history_capabilities(),
)
register_common_tools(agent)
register_rag_tool(agent, namespace="personal")
register_planner_tool(agent)  # slice_project: дочерние карточки на Deck-доску

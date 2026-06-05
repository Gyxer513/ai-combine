"""👴 Дед — Chronicler Agent (летописец).

Раз в день описывает в нарративе, что наработал комбайн и что менялось в проектах
Filipp; интерактивно — пересказывает события из летописи. Модель —
`nemotron-ultra-free` (1M контекст, free: летописцу важнее охват и качество
нарратива, чем скорость), резерв `qwen-max`. Чувствительность INTERNAL.
"""

from __future__ import annotations

from pydantic_ai import Agent

from ..tools.common import register_common_tools
from ..tools.rag import register_rag_tool
from .base import (
    AgentDeps,
    DataSensitivity,
    build_model,
    history_capabilities,
    load_prompt,
)

NAME = "ded"
TITLE = "👴 Дед"
SENSITIVITY = DataSensitivity.INTERNAL

# nemotron-3-ultra-550b (free, 1M контекст) основная, резерв qwen-max.
MODELS = ["nemotron-ultra-free", "qwen-max"]

agent = Agent(
    build_model(MODELS),
    deps_type=AgentDeps,
    instructions=load_prompt(NAME),
    name=NAME,
    capabilities=history_capabilities(),
)
register_common_tools(agent)
register_rag_tool(agent, namespace="personal")

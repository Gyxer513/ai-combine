"""👴 Дед — Chronicler Agent (летописец).

Интерактивно (чат/бот) пересказывает события из летописи — модель `qwen-plus`
(быстро и отзывчиво для диалога), резерв `qwen-max`.

Жирный `nemotron-ultra-free` (550B, 1M контекст) приберегаем для РАЗОВОЙ дневной
летописи в chronicle-worker (там охват и качество нарратива важнее скорости, а
free-тир медленный для интерактива) — см. `settings.chronicle_model`.
Чувствительность INTERNAL.
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

# Интерактив: быстрая qwen-plus, резерв qwen-max. (Ultra — только в chronicle-worker.)
MODELS = ["qwen-plus", "qwen-max"]

agent = Agent(
    build_model(MODELS),
    deps_type=AgentDeps,
    instructions=load_prompt(NAME),
    name=NAME,
    capabilities=history_capabilities(),
)
register_common_tools(agent)
register_rag_tool(agent, namespace="personal")

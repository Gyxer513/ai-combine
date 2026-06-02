"""🍞 Колобок — General Agent.

Общий помощник: ресёрч, поиск, бытовые вопросы. Чувствительность данных PUBLIC,
поэтому впереди стоят бесплатные модели. Цепочка моделей — из плана:
основная `owl-alpha-free` (1M контекст), резерв `qwen-plus` → `qwen-max`.

Инструменты Этапа 2: web_search и простая память (scratchpad-заметки).
RAG (`search_knowledge_base`) подключится на Этапе 3.
"""

from __future__ import annotations

from pydantic_ai import Agent

from ..tools.common import register_common_tools
from ..tools.rag import register_rag_tool
from .base import AgentDeps, DataSensitivity, build_model, load_prompt

NAME = "kolobok"
TITLE = "🍞 Колобок"
SENSITIVITY = DataSensitivity.PUBLIC

# Цепочка LiteLLM: основная + fallback'и (см. план, финальная раскладка Колобка).
MODELS = ["owl-alpha-free", "qwen-plus", "qwen-max"]

agent = Agent(
    build_model(MODELS),
    deps_type=AgentDeps,
    # instructions (а не system_prompt): применяются на КАЖДОМ запуске, в т.ч. когда
    # передаётся message_history (многоходовой /chat, путь OpenWebUI). С system_prompt
    # persona терялась на втором+ ходу и в OpenWebUI.
    instructions=load_prompt(NAME),
    name=NAME,
)
register_common_tools(agent)
register_rag_tool(agent, namespace="personal")

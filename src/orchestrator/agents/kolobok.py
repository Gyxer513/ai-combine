"""🍞 Колобок — General Agent.

Общий помощник: ресёрч, поиск, бытовые вопросы. Чувствительность данных PUBLIC,
поэтому впереди стоят бесплатные модели. Цепочка моделей — из плана:
основная `owl-alpha-free` (1M контекст), резерв `qwen-plus` → `qwen-max`.

Инструменты Этапа 2: web_search и простая память (scratchpad-заметки).
RAG (`search_knowledge_base`) подключится на Этапе 3.
"""

from __future__ import annotations

from pydantic_ai import Agent, RunContext

from .base import AgentDeps, DataSensitivity, build_model, load_prompt

NAME = "kolobok"
TITLE = "🍞 Колобок"
SENSITIVITY = DataSensitivity.PUBLIC

# Цепочка LiteLLM: основная + fallback'и (см. план, финальная раскладка Колобка).
MODELS = ["owl-alpha-free", "qwen-plus", "qwen-max"]

agent = Agent(
    build_model(MODELS),
    deps_type=AgentDeps,
    system_prompt=load_prompt(NAME),
    name=NAME,
)


@agent.tool
async def web_search(ctx: RunContext[AgentDeps], query: str, max_results: int = 5) -> str:
    """Поиск в интернете для актуальной информации.

    Args:
        query: Поисковый запрос на естественном языке.
        max_results: Сколько находок вернуть (1-10).
    """
    max_results = max(1, min(max_results, 10))
    results = await ctx.deps.web.search(query, max_results=max_results)
    if not results:
        return "Ничего не нашлось."
    return "\n\n".join(r.as_line() for r in results)


@agent.tool
async def save_note(ctx: RunContext[AgentDeps], key: str, value: str) -> str:
    """Запомнить факт в рамках текущего разговора (scratchpad).

    Args:
        key: Короткий ключ-ярлык.
        value: Что запомнить.
    """
    ctx.deps.store.save_note(ctx.deps.conversation_id, key, value)
    return f"Запомнил «{key}»."


@agent.tool
async def recall_note(ctx: RunContext[AgentDeps], key: str) -> str:
    """Вспомнить ранее сохранённый факт по ключу.

    Args:
        key: Ключ, под которым сохраняли заметку.
    """
    value = ctx.deps.store.get_note(ctx.deps.conversation_id, key)
    return value if value is not None else f"Заметки «{key}» нет."

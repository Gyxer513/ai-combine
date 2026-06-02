"""Общие инструменты, доступные всем агентам.

Регистрируются на любом `Agent[AgentDeps, str]` через `register_common_tools`,
чтобы Колобок/Кощей/Левша не дублировали один и тот же код. Специфичные
инструменты (RAG, Gitea, sandbox) добавляются в модулях конкретных агентов.
"""

from __future__ import annotations

from pydantic_ai import Agent, RunContext

from .web_search import WebSearchClient  # noqa: F401  (для подсказок типов)


def register_common_tools(agent: Agent) -> None:
    """Навесить web_search и scratchpad-память на агента."""

    @agent.tool
    async def web_search(ctx: RunContext, query: str, max_results: int = 5) -> str:
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
    async def save_note(ctx: RunContext, key: str, value: str) -> str:
        """Запомнить факт в рамках текущего разговора (scratchpad).

        Args:
            key: Короткий ключ-ярлык.
            value: Что запомнить.
        """
        ctx.deps.store.save_note(ctx.deps.conversation_id, key, value)
        return f"Запомнил «{key}»."

    @agent.tool
    async def recall_note(ctx: RunContext, key: str) -> str:
        """Вспомнить ранее сохранённый факт по ключу.

        Args:
            key: Ключ, под которым сохраняли заметку.
        """
        value = ctx.deps.store.get_note(ctx.deps.conversation_id, key)
        return value if value is not None else f"Заметки «{key}» нет."

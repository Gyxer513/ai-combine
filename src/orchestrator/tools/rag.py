"""Инструмент поиска по базе знаний (RAG).

`register_rag_tool(agent, namespace)` навешивает на агента `search_knowledge_base`,
жёстко привязанный к его namespace — модель не выбирает namespace сама и не
лезет в чужие данные (важно для recon: security-заметки не утекают General-агенту).
"""

from __future__ import annotations

from pydantic_ai import Agent, RunContext

from .guard import wrap_untrusted


def register_rag_tool(agent: Agent, namespace: str) -> None:
    """Навесить search_knowledge_base, привязанный к namespace агента."""

    @agent.tool
    async def search_knowledge_base(ctx: RunContext, query: str, top_k: int = 5) -> str:
        """Поиск по моей личной базе знаний (заметки, документы).

        Args:
            query: Что искать, на естественном языке.
            top_k: Сколько фрагментов вернуть (1-10).
        """
        if ctx.deps.embedder is None or ctx.deps.vstore is None:
            return "База знаний недоступна (RAG не сконфигурирован)."
        top_k = max(1, min(top_k, 10))
        vector = await ctx.deps.embedder.embed_one(query)
        hits = await ctx.deps.vstore.search(namespace, vector, top_k=top_k)
        if not hits:
            return "В базе знаний ничего не найдено."
        # Содержимое заметок/документов — данные, не команды (в заметку мог попасть
        # чужой текст с инъекцией). Оборачиваем как недоверенное.
        body = "\n\n".join(f"[источник: {h.path}]\n{h.text}" for h in hits)
        return wrap_untrusted("knowledge_base", body)

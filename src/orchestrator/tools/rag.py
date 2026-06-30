"""Knowledge base search tool (RAG).

`register_rag_tool(agent, namespace)` attaches `search_knowledge_base` to the agent,
hard-bound to its namespace — the model does not pick the namespace itself and does
not reach into other data (important for recon: security notes do not leak to the
General agent).
"""

from __future__ import annotations

from pydantic_ai import Agent, RunContext

from .guard import wrap_untrusted


def register_rag_tool(agent: Agent, namespace: str) -> None:
    """Attach search_knowledge_base bound to the agent's namespace."""

    @agent.tool
    async def search_knowledge_base(ctx: RunContext, query: str, top_k: int = 5) -> str:
        """Search my personal knowledge base (notes, documents).

        Args:
            query: What to search for, in natural language.
            top_k: How many fragments to return (1-10).
        """
        if ctx.deps.embedder is None or ctx.deps.vstore is None:
            return "Knowledge base unavailable (RAG is not configured)."
        top_k = max(1, min(top_k, 10))
        vector = await ctx.deps.embedder.embed_one(query)
        hits = await ctx.deps.vstore.search(namespace, vector, top_k=top_k)
        if not hits:
            return "Nothing found in the knowledge base."
        # Note/document content is data, not commands (a note may contain foreign
        # text with an injection). We wrap it as untrusted.
        body = "\n\n".join(f"[source: {h.path}]\n{h.text}" for h in hits)
        return wrap_untrusted("knowledge_base", body)

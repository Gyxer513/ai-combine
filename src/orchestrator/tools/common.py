"""Common tools available to all agents.

Registered on any `Agent[AgentDeps, str]` via `register_common_tools` so that
assistant/recon/coder do not duplicate the same code. Specific tools (RAG, Gitea,
sandbox) are added in the modules of the individual agents.
"""

from __future__ import annotations

from pydantic_ai import Agent, RunContext

from .guard import wrap_untrusted
from .web_search import WebSearchClient  # noqa: F401  (for type hints)


def register_common_tools(agent: Agent) -> None:
    """Attach web_search and scratchpad memory to the agent."""

    @agent.tool
    async def web_search(ctx: RunContext, query: str, max_results: int = 5) -> str:
        """Search the internet for up-to-date information.

        Args:
            query: Search query in natural language.
            max_results: How many results to return (1-10).
        """
        max_results = max(1, min(max_results, 10))
        results = await ctx.deps.web.search(query, max_results=max_results)
        if not results:
            return "Nothing found."
        # Internet results are untrusted: we wrap them so the agent does not take
        # instructions hidden in snippets for commands.
        return wrap_untrusted("web_search", "\n\n".join(r.as_line() for r in results))

    @agent.tool
    async def save_note(ctx: RunContext, key: str, value: str) -> str:
        """Remember a fact within the current conversation (scratchpad).

        Args:
            key: Short label key.
            value: What to remember.
        """
        ctx.deps.store.save_note(ctx.deps.conversation_id, key, value)
        return f"Remembered \"{key}\"."

    @agent.tool
    async def recall_note(ctx: RunContext, key: str) -> str:
        """Recall a previously saved fact by its key.

        Args:
            key: The key the note was saved under.
        """
        value = ctx.deps.store.get_note(ctx.deps.conversation_id, key)
        return value if value is not None else f"No note for \"{key}\"."

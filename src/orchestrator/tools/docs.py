"""`search_docs` tool: semantic search over the combine's own Markdown docs.

Backed by a prebuilt FAISS index + a local EmbeddingGemma ONNX embedder (see
`src/docs_search/`). Fully optional and fail-soft: if the `docs` extra isn't installed,
the feature is disabled, or the index hasn't been built, the tool returns a friendly
message instead of erroring. The embedder/index are loaded once and reused.

Embedding + FAISS search are CPU-bound and synchronous, so they run in a worker thread
to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache

import structlog
from pydantic_ai import Agent, RunContext

from ..config import settings
from .guard import wrap_untrusted

log = structlog.get_logger()


@lru_cache(maxsize=1)
def _embedder():
    from src.docs_search.embedder import DocsEmbedder

    return DocsEmbedder()


@lru_cache(maxsize=1)
def _index():
    """Load the prebuilt index once. None if not built; raises if the extra is missing."""
    from src.docs_search.store import DocsIndex

    return DocsIndex.load(settings.docs_index_dir)


def _search_sync(query: str, top_k: int) -> str:
    index = _index()  # may raise DocsEmbedderUnavailable if extra not installed
    if index is None:
        return "The docs index hasn't been built yet (run: python -m src.docs_search.index)."
    qv = _embedder().embed_one(query, kind="query")
    hits = index.search(qv, top_k=max(1, min(top_k, 10)))
    if not hits:
        return "Nothing relevant found in the docs."
    body = "\n\n".join(
        f"[{h.source}{(' > ' + h.heading) if h.heading else ''}]\n{h.text}" for h in hits
    )
    return wrap_untrusted("combine_docs", body)


async def run_search(query: str, top_k: int = 5) -> str:
    """Gate + off-thread docs search. Module-level so it's testable without an agent."""
    if not settings.docs_search_enabled:
        return "Docs search is disabled (set DOCS_SEARCH_ENABLED=true and build the index)."
    try:
        return await asyncio.to_thread(_search_sync, query, top_k)
    except Exception as exc:  # noqa: BLE001 — missing extra / load failure shouldn't crash chat
        log.warning("docs.search_failed", error=str(exc))
        return f"Docs search unavailable: {exc}"


def register_docs_tool(agent: Agent) -> None:
    """Attach search_docs to an agent (semantic search over the project's own docs)."""

    @agent.tool
    async def search_docs(ctx: RunContext, query: str, top_k: int = 5) -> str:
        """Search AI Combine's own documentation (README, docs/, SECURITY) semantically.

        Use this to answer questions about how this very system works — its agents,
        configuration, architecture, sandbox, security model, deployment.

        Args:
            query: Natural-language question about the project.
            top_k: How many doc snippets to return (1-10).
        """
        return await run_search(query, top_k)

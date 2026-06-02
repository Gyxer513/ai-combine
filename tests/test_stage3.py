"""Тесты Этапа 3 (RAG): чанкер, embedder, инструмент search_knowledge_base."""

from __future__ import annotations

import httpx
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from src.orchestrator.agents import kolobok
from src.orchestrator.agents.base import AgentDeps
from src.orchestrator.rag.embedder import EmbeddingClient
from src.orchestrator.rag.store import Hit, point_id
from src.orchestrator.tools.memory import ConversationStore
from src.orchestrator.tools.web_search import WebSearchClient
from src.rag_indexer.chunker import chunk_text

# --- чанкер ---


def test_chunker_splits_and_overlaps():
    text = " ".join(f"слово{i}" for i in range(500))
    chunks = chunk_text(text, max_tokens=50, overlap=10)
    assert len(chunks) > 1
    assert all(c.strip() for c in chunks)


def test_chunker_empty():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_point_id_deterministic():
    assert point_id("note:1", 0) == point_id("note:1", 0)
    assert point_id("note:1", 0) != point_id("note:1", 1)


# --- embedder ---


async def test_embedder_preserves_order():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"index": 1, "embedding": [0.2]}, {"index": 0, "embedding": [0.1]}]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = EmbeddingClient(http, base_url="http://x/v1", api_key="k")
        vectors = await client.embed(["a", "b"])
    assert vectors == [[0.1], [0.2]]  # отсортированы по index


# --- инструмент search_knowledge_base ---


class _StubEmbedder:
    async def embed_one(self, text: str) -> list[float]:
        return [0.0, 0.1, 0.2]


class _StubStore:
    def __init__(self, hits: list[Hit]) -> None:
        self._hits = hits
        self.asked_namespace: str | None = None

    async def search(self, namespace: str, vector, *, top_k: int = 5) -> list[Hit]:
        self.asked_namespace = namespace
        return self._hits


def _deps_with_rag(store: _StubStore) -> AgentDeps:
    return AgentDeps(
        conversation_id="t",
        web=WebSearchClient(httpx.AsyncClient()),
        store=ConversationStore(),
        embedder=_StubEmbedder(),
        vstore=store,
    )


async def test_search_knowledge_base_returns_hits():
    hit = Hit(text="моя заметка про Python", path="Notes/Personal/Py", source="notes", score=0.9)
    stub = _StubStore([hit])
    captured: dict = {}

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        for m in messages:
            for p in m.parts:
                if isinstance(p, ToolReturnPart):
                    captured["tool_result"] = p.content
                    return ModelResponse(parts=[TextPart(content="готово")])
        return ModelResponse(
            parts=[ToolCallPart(tool_name="search_knowledge_base", args={"query": "питон"})]
        )

    with kolobok.agent.override(model=FunctionModel(fn)):
        result = await kolobok.agent.run("вопрос", deps=_deps_with_rag(stub))

    assert stub.asked_namespace == "personal"  # Колобок ищет в personal
    assert "моя заметка про Python" in captured["tool_result"]
    assert result.output == "готово"

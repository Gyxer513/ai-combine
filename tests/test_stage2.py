"""Тесты Этапа 2: инструменты, память, агент и API (без реальных LLM/сети)."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from src.orchestrator.agents import kolobok
from src.orchestrator.agents.base import shared_store
from src.orchestrator.main import app
from src.orchestrator.tools.memory import ConversationStore
from src.orchestrator.tools.web_search import WebSearchClient, _parse_instant_answer

# --- web_search ---

SAMPLE_IA = {
    "Heading": "Python",
    "AbstractText": "Python is a programming language.",
    "AbstractURL": "https://example.com/python",
    "RelatedTopics": [
        {"Text": "Pip - package installer", "FirstURL": "https://example.com/pip"},
        {"Topics": [{"Text": "Venv - virtual env", "FirstURL": "https://example.com/venv"}]},
    ],
}


def test_parse_instant_answer():
    results = _parse_instant_answer(SAMPLE_IA, max_results=5)
    assert results[0].title == "Python"
    assert results[0].url == "https://example.com/python"
    # вложенные RelatedTopics разворачиваются в плоский список
    urls = {r.url for r in results}
    assert "https://example.com/pip" in urls
    assert "https://example.com/venv" in urls


SEARX_SAMPLE = {
    "results": [
        {"title": "Python", "url": "https://ex/py", "content": "language"},
        {"title": "Pip", "url": "https://ex/pip", "content": "installer"},
    ]
}


async def test_web_search_uses_searxng():
    def handler(request: httpx.Request) -> httpx.Response:
        if "/search" in request.url.path:
            return httpx.Response(200, json=SEARX_SAMPLE)
        return httpx.Response(200, json={})  # ddg не должен понадобиться

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        results = await WebSearchClient(http).search("python", max_results=3)
    assert results[0].url == "https://ex/py"
    assert results[0].snippet == "language"


async def test_web_search_falls_back_to_ddg_when_searxng_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        if "/search" in request.url.path:
            return httpx.Response(200, json={"results": []})  # SearXNG пусто
        return httpx.Response(200, json=SAMPLE_IA)  # DDG отдаёт

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        results = await WebSearchClient(http).search("python")
    assert any("example.com/python" in r.url for r in results)


async def test_web_search_all_fail_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        results = await WebSearchClient(http).search("anything")
    assert results == []


# --- ConversationStore ---


def test_store_history_trims():
    store = ConversationStore(max_messages=2)
    msgs: list[ModelMessage] = [ModelResponse(parts=[TextPart(content=str(i))]) for i in range(5)]
    store.extend_history("c1", msgs)
    assert len(store.history("c1")) == 2


def test_store_notes_and_clear():
    store = ConversationStore()
    store.save_note("c1", "city", "Vladivostok")
    assert store.get_note("c1", "city") == "Vladivostok"
    store.clear("c1")
    assert store.get_note("c1", "city") is None


# --- агент через тестовую модель ---


@pytest.fixture(autouse=True)
def _reset_store():
    shared_store().clear("test-conv")
    yield
    shared_store().clear("test-conv")


def test_chat_with_test_model():
    test_model = TestModel(call_tools=[], custom_output_text="Привет!")
    with kolobok.agent.override(model=test_model):
        with TestClient(app) as client:
            resp = client.post(
                "/chat",
                json={"message": "ping", "conversation_id": "test-conv"},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["agent"] == "kolobok"
    assert body["reply"] == "Привет!"
    assert body["conversation_id"] == "test-conv"


def test_chat_multiturn_grows_history():
    seen_lengths: list[int] = []

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen_lengths.append(len(messages))
        return ModelResponse(parts=[TextPart(content="ok")])

    with kolobok.agent.override(model=FunctionModel(fn)):
        with TestClient(app) as client:
            client.post("/chat", json={"message": "first", "conversation_id": "test-conv"})
            client.post("/chat", json={"message": "second", "conversation_id": "test-conv"})

    # второй ход видит больше сообщений, чем первый (история подмешана)
    assert seen_lengths[1] > seen_lengths[0]


def test_agents_endpoint():
    with TestClient(app) as client:
        resp = client.get("/agents")
    assert resp.status_code == 200
    names = {a["name"] for a in resp.json()}
    assert "kolobok" in names


def test_openai_models():
    with TestClient(app) as client:
        resp = client.get("/v1/models")
    body = resp.json()
    assert body["object"] == "list"
    assert any(m["id"] == "kolobok" for m in body["data"])


def test_openai_chat_completions_non_stream():
    test_model = TestModel(call_tools=[], custom_output_text="Ответ")
    with kolobok.agent.override(model=test_model):
        with TestClient(app) as client:
            resp = client.post(
                "/v1/chat/completions",
                json={
                    "model": "kolobok",
                    "messages": [{"role": "user", "content": "вопрос"}],
                    "stream": False,
                },
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "Ответ"


def test_openai_chat_completions_stream():
    test_model = TestModel(call_tools=[], custom_output_text="поток")
    with kolobok.agent.override(model=test_model):
        with TestClient(app) as client:
            resp = client.post(
                "/v1/chat/completions",
                json={
                    "model": "kolobok",
                    "messages": [{"role": "user", "content": "вопрос"}],
                    "stream": True,
                },
            )
    assert resp.status_code == 200
    text = resp.text
    assert "chat.completion.chunk" in text
    assert "data: [DONE]" in text

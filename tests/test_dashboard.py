"""Тесты дашборда: метрики, статистика стора и роуты."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.orchestrator.api import dashboard
from src.orchestrator.main import app
from src.orchestrator.metrics import Metrics
from src.orchestrator.persistence import Database
from src.orchestrator.tools.memory import ConversationStore


def _mem_db() -> Database:
    return Database(":memory:")


def test_metrics_record_accumulates():
    m = Metrics(_mem_db())
    m.record("assistant", 100, 50)
    m.record("assistant", 10, 5)
    a = m.for_agent("assistant")
    assert a.requests == 2
    assert a.input_tokens == 110
    assert a.output_tokens == 55
    assert a.last_used is not None
    assert m.uptime_sec() >= 0


def test_metrics_unknown_agent_zero():
    a = Metrics(_mem_db()).for_agent("нет")
    assert a.requests == 0 and a.input_tokens == 0


def test_store_stats():
    store = ConversationStore(_mem_db())
    from pydantic_ai.messages import ModelRequest, UserPromptPart

    msg = ModelRequest(parts=[UserPromptPart(content="hi")])
    store.extend_history("c1", [msg, msg])
    store.extend_history("c2", [msg])
    convs, messages = store.stats()
    assert convs == 2
    assert messages == 3


def test_dashboard_page_is_html():
    with TestClient(app) as client:
        resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "AI Combine" in resp.text


def test_api_dashboard_structure(monkeypatch):
    async def fake_services(http):
        return [{"name": "LiteLLM", "up": True}, {"name": "Qdrant", "up": False}]

    async def fake_rag():
        return [{"namespace": "personal", "points": 419}]

    monkeypatch.setattr(dashboard, "_services", fake_services)
    monkeypatch.setattr(dashboard, "_rag", fake_rag)

    with TestClient(app) as client:
        resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert {"uptime_sec", "services", "agents", "rag", "conversations", "messages"} <= data.keys()
    # три агента из реестра
    names = {a["name"] for a in data["agents"]}
    assert {"assistant", "recon", "coder"} <= names
    assert data["services"][0]["name"] == "LiteLLM"
    assert data["rag"][0]["points"] == 419

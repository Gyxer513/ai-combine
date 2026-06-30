"""Planner tests: decomposing a project into Deck cards (slice_project)."""

from __future__ import annotations

import httpx
import pytest

import src.orchestrator.tools.deck as deck_tool
from src.deck_worker.client import DeckClient
from src.orchestrator.config import settings
from src.orchestrator.tools.deck import Subtask, plan_to_cards


def _mock_client(handler):
    """httpx.AsyncClient factory on MockTransport (replaces the constructor in the tool).

    We capture the real class BEFORE patching, otherwise the factory would call itself.
    """
    real_cls = httpx.AsyncClient

    def factory(*args, **kwargs):
        return real_cls(transport=httpx.MockTransport(handler))

    return factory


@pytest.fixture
def _nc(monkeypatch):
    monkeypatch.setattr(settings, "nextcloud_url", "http://nc.test")
    monkeypatch.setattr(settings, "nextcloud_user", "u")
    monkeypatch.setattr(settings, "nextcloud_app_password", "p")
    monkeypatch.setattr(settings, "deck_board", "AI Combine Tasks")
    monkeypatch.setattr(settings, "deck_todo_stack", "To Do")
    monkeypatch.setattr(settings, "deck_label_agent_map", "sec:recon,code:coder,ask:assistant")


async def test_plan_to_cards_creates_and_labels(monkeypatch, _nc):
    calls = {"cards": [], "labels": []}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/boards"):
            board = {
                "id": 7,
                "title": "AI Combine Tasks",
                "labels": [{"id": 11, "title": "code"}],
            }
            return httpx.Response(200, json=[board])
        if path.endswith("/boards/7/stacks"):
            return httpx.Response(200, json=[{"id": 70, "title": "To Do", "cards": []}])
        if path.endswith("/cards") and request.method == "POST":
            calls["cards"].append(request.url.path)
            return httpx.Response(200, json={"id": 900 + len(calls["cards"])})
        if path.endswith("/assignLabel") and request.method == "PUT":
            calls["labels"].append(path)
            return httpx.Response(200, json={})
        return httpx.Response(404)

    monkeypatch.setattr(deck_tool.httpx, "AsyncClient", _mock_client(handler))

    out = await plan_to_cards(
        "MIS report",
        [
            Subtask(title="DB schema", agent="coder", acceptance="DDL exists"),
            Subtask(title="Requirements gathering", agent="assistant"),
        ],
    )
    assert "Created 2 cards" in out
    assert len(calls["cards"]) == 2
    # the code label exists on the board -> assigned to the coder card; assistant (ask) has none
    assert len(calls["labels"]) == 1
    assert "label not on the board" in out  # for the assistant subtask


async def test_plan_to_cards_rejects_unknown_agent(_nc):
    out = await plan_to_cards("X", [Subtask(title="t", agent="wizard")])
    assert "Unknown executors" in out and "wizard" in out


async def test_plan_to_cards_no_nextcloud(monkeypatch):
    monkeypatch.setattr(settings, "nextcloud_url", "")
    out = await plan_to_cards("X", [Subtask(title="t", agent="coder")])
    assert "Deck unavailable" in out


async def test_deck_client_assign_label_request():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["method"] = request.method
        return httpx.Response(200, json={})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    deck = DeckClient(http, "http://nc.test", "u", "p")
    await deck.assign_label(7, 70, 900, 11)
    assert seen["method"] == "PUT"
    assert seen["path"].endswith("/boards/7/stacks/70/cards/900/assignLabel")

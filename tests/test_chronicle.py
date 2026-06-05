"""Тесты chronicle-worker: сбор активности, дайджест, дозапись летописи, ДЕД."""

from __future__ import annotations

import httpx

import src.chronicle_worker.main as cw
from src.chronicle_worker.notes import NotesClient
from src.orchestrator.agents.registry import REGISTRY
from src.orchestrator.config import settings


def test_ded_registered():
    assert "ded" in REGISTRY
    assert REGISTRY["ded"].models[0] == "nemotron-ultra-free"


def test_build_digest_blocks():
    d = cw.build_digest(["Задача А"], ["Идея Б"], ["Заметка В  [career]"])
    assert "Задача А" in d and "Идея Б" in d and "Заметка В" in d


def test_build_digest_empty():
    d = cw.build_digest([], [], [])
    assert d.count("(ничего)") == 3


class _FakeDeck:
    def __init__(self, boards: dict[str, int], stacks: dict[int, list[dict]]) -> None:
        self._boards = boards
        self._stacks = stacks

    async def find_board(self, title):
        bid = self._boards.get(title)
        return {"id": bid} if bid else None

    async def stacks(self, board_id):
        return self._stacks.get(board_id, [])


async def test_gather_combine_filters_by_time():
    cutoff = 1000.0
    tasks_stacks = [
        {"title": settings.deck_done_stack, "cards": [
            {"title": "Свежая задача", "lastModified": 1500},
            {"title": "Старая задача", "lastModified": 500},  # до cutoff -> отсеять
        ]},
        {"title": settings.deck_doing_stack,
         "cards": [{"title": "В работе", "lastModified": 2000}]},
    ]
    ideas_stacks = [{"title": "Новые", "cards": [{"title": "Идея X", "createdAt": 1500}]}]
    deck = _FakeDeck(
        boards={settings.deck_board: 1, settings.research_board: 2},
        stacks={1: tasks_stacks, 2: ideas_stacks},
    )
    done, ideas = await cw.gather_combine(deck, cutoff)
    assert done == ["Свежая задача"]  # только Done и только свежая
    assert ideas == ["Идея X"]


class _FakeNotes:
    def __init__(self, notes: list[dict]) -> None:
        self._notes = notes

    async def list_notes(self):
        return self._notes


async def test_gather_projects_excludes_chronicle_and_old():
    cutoff = 1000.0
    notes = _FakeNotes([
        {"title": "Карьерный план", "category": "career", "modified": 1500},
        {"title": settings.chronicle_note, "category": "AI Projects",
         "modified": 1500},  # сама летопись — исключить
        {"title": "Старая заметка", "category": "", "modified": 500},  # до cutoff
    ])
    out = await cw.gather_projects(notes, cutoff)
    assert any("Карьерный план" in x for x in out)
    assert all(settings.chronicle_note not in x for x in out)
    assert all("Старая заметка" not in x for x in out)


async def test_notes_append_prepends_new_section():
    state = {"content": "# Летопись AI Combine\n\n## 2026-06-01\n\nстарая запись\n"}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=[{"id": 7, "title": "Летопись AI Combine",
                                              "content": state["content"]}])
        if request.method == "PUT":
            import json as _json
            state["content"] = _json.loads(request.read())["content"]
            return httpx.Response(200, json={"id": 7})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        notes = NotesClient(http, "http://nc", "u", "p")
        await notes.append_section(
            title="Летопись AI Combine", category="AI Projects",
            heading="2026-06-02", body="новая запись",
        )
    # новая запись выше старой, обе на месте
    assert state["content"].index("2026-06-02") < state["content"].index("2026-06-01")
    assert "старая запись" in state["content"]

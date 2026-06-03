"""Тесты research-worker: ротация тем, парсинг, антидубль, создание карточек."""

from __future__ import annotations

import httpx

import src.research_worker.main as rw


def test_pick_theme_rotates():
    themes = ["a", "b", "c"]
    assert rw.pick_theme(themes, 0) == "a"
    assert rw.pick_theme(themes, 1) == "b"
    assert rw.pick_theme(themes, 3) == "a"  # по кругу


def test_build_prompt_has_theme_and_existing():
    p = rw.build_prompt("автоматизация", "сниппеты", ["Идея X"], 2)
    assert "автоматизация" in p
    assert "Идея X" in p
    assert "2" in p


def test_parse_ideas_valid():
    content = '[{"title":"A","pitch":"p","effort":"низкие","potential":"50к","source":"u"}]'
    ideas = rw.parse_ideas(content)
    assert len(ideas) == 1
    assert ideas[0].title == "A"
    assert "p" in ideas[0].as_description()


def test_parse_ideas_in_codefence_and_noise():
    content = "Вот идеи:\n```json\n[{\"title\":\"B\",\"pitch\":\"x\"}]\n```\nготово"
    ideas = rw.parse_ideas(content)
    assert [i.title for i in ideas] == ["B"]


def test_parse_ideas_garbage():
    assert rw.parse_ideas("нет json") == []
    assert rw.parse_ideas("") == []


class _FakeDeck:
    def __init__(self, existing: set[str]) -> None:
        self._existing = existing
        self.created: list[tuple[str, str]] = []

    async def find_board(self, title):
        return {"id": 1}

    async def stacks(self, board_id):
        return [{"id": 10, "title": "Новые", "cards": []}]

    async def board_card_titles(self, board_id):
        return set(self._existing)

    async def create_card(self, board_id, stack_id, title, description="", *, order=0):
        self.created.append((title, description))
        return {"id": len(self.created)}


async def test_run_once_creates_only_new(monkeypatch):
    deck = _FakeDeck(existing={"Старая идея"})

    async def fake_snippets(web, theme, n):
        return "результаты поиска"

    async def fake_model(http, system, user):
        return (
            '[{"title":"Новая идея","pitch":"п","effort":"низкие",'
            '"potential":"50к/мес","source":"u"},'
            '{"title":"старая идея","pitch":"дубль"}]'  # дубль по регистру -> отсеять
        )

    monkeypatch.setattr(rw, "gather_snippets", fake_snippets)
    monkeypatch.setattr(rw, "call_model", fake_model)

    async with httpx.AsyncClient() as http:
        created = await rw.run_once(http, deck, ordinal=0)

    assert created == 1
    assert deck.created[0][0] == "Новая идея"
    assert len(deck.created) == 1

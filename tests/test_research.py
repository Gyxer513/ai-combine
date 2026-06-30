"""Research-worker tests: theme rotation, parsing, de-duplication, card creation."""

from __future__ import annotations

import httpx

import src.research_worker.main as rw


def test_pick_theme_rotates():
    themes = ["a", "b", "c"]
    assert rw.pick_theme(themes, 0) == "a"
    assert rw.pick_theme(themes, 1) == "b"
    assert rw.pick_theme(themes, 3) == "a"  # wraps around


def test_build_prompt_has_theme_and_existing():
    p = rw.build_prompt("automation", "snippets", ["Idea X"], 2)
    assert "automation" in p
    assert "Idea X" in p
    assert "2" in p


def test_parse_ideas_valid():
    content = '[{"title":"A","pitch":"p","effort":"low","potential":"50k","source":"u"}]'
    ideas = rw.parse_ideas(content)
    assert len(ideas) == 1
    assert ideas[0].title == "A"
    assert "p" in ideas[0].as_description()


def test_parse_ideas_in_codefence_and_noise():
    content = "Here are the ideas:\n```json\n[{\"title\":\"B\",\"pitch\":\"x\"}]\n```\ndone"
    ideas = rw.parse_ideas(content)
    assert [i.title for i in ideas] == ["B"]


def test_parse_ideas_garbage():
    assert rw.parse_ideas("no json here") == []
    assert rw.parse_ideas("") == []


class _FakeDeck:
    def __init__(self, existing: set[str]) -> None:
        self._existing = existing
        self.created: list[tuple[str, str]] = []

    async def find_board(self, title):
        return {"id": 1}

    async def stacks(self, board_id):
        return [{"id": 10, "title": "New", "cards": []}]

    async def board_card_titles(self, board_id):
        return set(self._existing)

    async def create_card(self, board_id, stack_id, title, description="", *, order=0):
        self.created.append((title, description))
        return {"id": len(self.created)}


async def test_run_once_creates_only_new(monkeypatch):
    deck = _FakeDeck(existing={"Old idea"})

    async def fake_snippets(web, theme, n):
        return "search results"

    async def fake_model(http, system, user):
        return (
            '[{"title":"New idea","pitch":"p","effort":"low",'
            '"potential":"50k/mo","source":"u"},'
            '{"title":"old idea","pitch":"dup"}]'  # case-insensitive duplicate -> filtered
        )

    monkeypatch.setattr(rw, "gather_snippets", fake_snippets)
    monkeypatch.setattr(rw, "call_model", fake_model)

    async with httpx.AsyncClient() as http:
        created = await rw.run_once(http, deck, ordinal=0)

    assert created == 1
    assert deck.created[0][0] == "New idea"
    assert len(deck.created) == 1

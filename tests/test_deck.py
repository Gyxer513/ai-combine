"""Deck-worker tests: label routing, response parsing, card-processing logic."""

from __future__ import annotations

import httpx

from src.deck_worker.client import DeckClient, _unwrap
from src.deck_worker.main import agent_for_card, card_prompt, process_card

# --- label routing ---


def test_agent_for_card_by_label():
    mapping = {"sec": "recon", "code": "coder", "ask": "assistant"}
    card = {"labels": [{"title": "code"}]}
    assert agent_for_card(card, mapping, "assistant") == "coder"


def test_agent_for_card_label_case_insensitive():
    card = {"labels": [{"title": "SEC"}]}
    assert agent_for_card(card, {"sec": "recon"}, "assistant") == "recon"


def test_agent_for_card_default_when_no_label():
    assert agent_for_card({"labels": []}, {"sec": "recon"}, "assistant") == "assistant"
    assert agent_for_card({}, {"sec": "recon"}, "assistant") == "assistant"


def test_card_prompt_joins_title_and_description():
    assert card_prompt({"title": "T", "description": "D"}) == "T\n\nD"
    assert card_prompt({"title": "T", "description": ""}) == "T"


# --- Deck response parsing ---


def test_unwrap_handles_both_shapes():
    assert _unwrap({"result": [1, 2]}) == [1, 2]  # MCP wrapper
    assert _unwrap([1, 2]) == [1, 2]  # raw API


async def test_deck_client_find_board():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/boards")
        return httpx.Response(200, json=[{"id": 1, "title": "A"}, {"id": 2, "title": "Tasks"}])

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    deck = DeckClient(http, "http://nc.test", "u", "p")
    board = await deck.find_board("Tasks")
    assert board["id"] == 2


# --- card-processing logic ---


class _FakeDeck:
    def __init__(self) -> None:
        self.moves: list[tuple] = []
        self.comments: list[tuple] = []

    async def move_card(self, board_id, card_id, target_stack_id, *, order=0):
        self.moves.append((card_id, target_stack_id))

    async def add_comment(self, card_id, message):
        self.comments.append((card_id, message))


class _FakeOrch:
    def __init__(self, reply="Tokyo", fail=False) -> None:
        self._reply = reply
        self._fail = fail
        self.calls: list[tuple] = []

    async def chat(self, message, agent, conversation_id):
        self.calls.append((message, agent, conversation_id))
        if self._fail:
            raise RuntimeError("boom")
        return self._reply


async def _process(deck, orch, card, *, failed_id=57):
    await process_card(
        deck, orch, card,
        board_id=22, doing_id=55, done_id=56, failed_id=failed_id,
        mapping={"sec": "recon", "code": "coder", "ask": "assistant"},
        default="assistant",
    )


async def test_process_card_happy_path():
    deck, orch = _FakeDeck(), _FakeOrch(reply="Tokyo")
    card = {"id": 98, "title": "Capital of Japan?", "labels": [{"title": "ask"}]}
    await _process(deck, orch, card)
    # claim into In Progress (55), then move to Done (56)
    assert deck.moves == [(98, 55), (98, 56)]
    # agent chosen by label, conversation_id bound to the card
    assert orch.calls[0][1] == "assistant"
    assert orch.calls[0][2] == "deck:98"
    # result in the comment
    assert "Tokyo" in deck.comments[0][1]


async def test_process_card_failure_moves_to_failed_not_done():
    deck, orch = _FakeDeck(), _FakeOrch(fail=True)
    await _process(deck, orch, {"id": 99, "title": "X", "labels": [{"title": "sec"}]})
    # claim into In Progress (55), then to Failed (57) — NOT to Done (56)
    assert deck.moves == [(99, 55), (99, 57)]
    assert "❌" in deck.comments[0][1]  # with an error marker


async def test_process_card_failure_no_failed_stack_stays_in_progress():
    # no Failed stack -> the card stays in In Progress, does NOT move to Done
    deck, orch = _FakeDeck(), _FakeOrch(fail=True)
    await _process(deck, orch, {"id": 100, "title": "X", "labels": []}, failed_id=None)
    assert deck.moves == [(100, 55)]  # only the claim, no further move
    assert "❌" in deck.comments[0][1]

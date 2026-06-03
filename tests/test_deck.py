"""Тесты Deck-worker: роутинг по меткам, парсинг ответа, логика обработки карточки."""

from __future__ import annotations

import httpx

from src.deck_worker.client import DeckClient, _unwrap
from src.deck_worker.main import agent_for_card, card_prompt, process_card

# --- роутинг по меткам ---


def test_agent_for_card_by_label():
    mapping = {"sec": "koschei", "code": "levsha", "ask": "kolobok"}
    card = {"labels": [{"title": "code"}]}
    assert agent_for_card(card, mapping, "kolobok") == "levsha"


def test_agent_for_card_label_case_insensitive():
    card = {"labels": [{"title": "SEC"}]}
    assert agent_for_card(card, {"sec": "koschei"}, "kolobok") == "koschei"


def test_agent_for_card_default_when_no_label():
    assert agent_for_card({"labels": []}, {"sec": "koschei"}, "kolobok") == "kolobok"
    assert agent_for_card({}, {"sec": "koschei"}, "kolobok") == "kolobok"


def test_card_prompt_joins_title_and_description():
    assert card_prompt({"title": "T", "description": "D"}) == "T\n\nD"
    assert card_prompt({"title": "T", "description": ""}) == "T"


# --- разбор ответа Deck ---


def test_unwrap_handles_both_shapes():
    assert _unwrap({"result": [1, 2]}) == [1, 2]  # MCP-обёртка
    assert _unwrap([1, 2]) == [1, 2]  # сырой API


async def test_deck_client_find_board():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/boards")
        return httpx.Response(200, json=[{"id": 1, "title": "A"}, {"id": 2, "title": "Задачи"}])

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    deck = DeckClient(http, "http://nc.test", "u", "p")
    board = await deck.find_board("Задачи")
    assert board["id"] == 2


# --- логика обработки карточки ---


class _FakeDeck:
    def __init__(self) -> None:
        self.moves: list[tuple] = []
        self.comments: list[tuple] = []

    async def move_card(self, board_id, stack_id, card_id, target_stack_id, *, order=0):
        self.moves.append((stack_id, target_stack_id, card_id))

    async def add_comment(self, card_id, message):
        self.comments.append((card_id, message))


class _FakeOrch:
    def __init__(self, reply="Токио", fail=False) -> None:
        self._reply = reply
        self._fail = fail
        self.calls: list[tuple] = []

    async def chat(self, message, agent, conversation_id):
        self.calls.append((message, agent, conversation_id))
        if self._fail:
            raise RuntimeError("boom")
        return self._reply


async def _process(deck, orch, card):
    await process_card(
        deck, orch, card,
        board_id=22, todo_id=54, doing_id=55, done_id=56,
        mapping={"sec": "koschei", "code": "levsha", "ask": "kolobok"},
        default="kolobok",
    )


async def test_process_card_happy_path():
    deck, orch = _FakeDeck(), _FakeOrch(reply="Токио")
    await _process(deck, orch, {"id": 98, "title": "Столица Японии?", "labels": [{"title": "ask"}]})
    # claim в In Progress, затем перенос в Done
    assert deck.moves == [(54, 55, 98), (55, 56, 98)]
    # агент выбран по метке, conversation_id привязан к карточке
    assert orch.calls[0][1] == "kolobok"
    assert orch.calls[0][2] == "deck:98"
    # результат в комментарии
    assert "Токио" in deck.comments[0][1]


async def test_process_card_failure_still_moves_to_done():
    deck, orch = _FakeDeck(), _FakeOrch(fail=True)
    await _process(deck, orch, {"id": 99, "title": "X", "labels": [{"title": "sec"}]})
    assert deck.moves == [(54, 55, 99), (55, 56, 99)]  # всё равно доехала до Done
    assert "❌" in deck.comments[0][1]  # с пометкой об ошибке

"""Тесты Deck-worker: роутинг по меткам, парсинг ответа, логика обработки карточки."""

from __future__ import annotations

import httpx

from src.deck_worker.client import DeckClient, _unwrap
from src.deck_worker.main import agent_for_card, card_prompt, process_card

# --- роутинг по меткам ---


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

    async def move_card(self, board_id, card_id, target_stack_id, *, order=0):
        self.moves.append((card_id, target_stack_id))

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


async def _process(deck, orch, card, *, failed_id=57):
    await process_card(
        deck, orch, card,
        board_id=22, doing_id=55, done_id=56, failed_id=failed_id,
        mapping={"sec": "recon", "code": "coder", "ask": "assistant"},
        default="assistant",
    )


async def test_process_card_happy_path():
    deck, orch = _FakeDeck(), _FakeOrch(reply="Токио")
    await _process(deck, orch, {"id": 98, "title": "Столица Японии?", "labels": [{"title": "ask"}]})
    # claim в In Progress (55), затем перенос в Done (56)
    assert deck.moves == [(98, 55), (98, 56)]
    # агент выбран по метке, conversation_id привязан к карточке
    assert orch.calls[0][1] == "assistant"
    assert orch.calls[0][2] == "deck:98"
    # результат в комментарии
    assert "Токио" in deck.comments[0][1]


async def test_process_card_failure_moves_to_failed_not_done():
    deck, orch = _FakeDeck(), _FakeOrch(fail=True)
    await _process(deck, orch, {"id": 99, "title": "X", "labels": [{"title": "sec"}]})
    # claim в In Progress (55), затем в Failed (57) — НЕ в Done (56)
    assert deck.moves == [(99, 55), (99, 57)]
    assert "❌" in deck.comments[0][1]  # с пометкой об ошибке


async def test_process_card_failure_no_failed_stack_stays_in_progress():
    # стека Failed нет -> карточка остаётся в In Progress, НЕ уезжает в Done
    deck, orch = _FakeDeck(), _FakeOrch(fail=True)
    await _process(deck, orch, {"id": 100, "title": "X", "labels": []}, failed_id=None)
    assert deck.moves == [(100, 55)]  # только claim, дальше не двигаем
    assert "❌" in deck.comments[0][1]

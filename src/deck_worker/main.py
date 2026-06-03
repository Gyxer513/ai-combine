"""Entrypoint Deck-worker'а.

Цикл (или один проход при deck_poll_interval_min=0):
    карточки из To Do -> claim (In Progress) -> агент через оркестратор ->
    комментарий с результатом -> Done.

Claim переносом в In Progress защищает от повторной обработки на следующем тике.
"""

from __future__ import annotations

import asyncio
import contextlib

import httpx
import structlog

from src.orchestrator.config import settings

from .client import DeckClient

log = structlog.get_logger()

_REPLY_TIMEOUT = 600  # агент (особенно Кощей со сканами) может работать минуты


class OrchestratorClient:
    """Минимальный клиент к оркестратору (/chat)."""

    def __init__(self, http: httpx.AsyncClient, base_url: str) -> None:
        self._http = http
        self._base = base_url.rstrip("/")

    async def chat(self, message: str, agent: str, conversation_id: str) -> str:
        resp = await self._http.post(
            f"{self._base}/chat",
            json={"message": message, "agent": agent, "conversation_id": conversation_id},
            timeout=_REPLY_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json().get("reply", "")


def agent_for_card(card: dict, mapping: dict[str, str], default: str) -> str:
    """Выбрать агента по меткам карточки (первая совпавшая метка), иначе default."""
    titles = {(label.get("title") or "").lower() for label in (card.get("labels") or [])}
    for label, agent in mapping.items():
        if label in titles:
            return agent
    return default


def card_prompt(card: dict) -> str:
    """Текст задачи для агента: заголовок + описание."""
    title = card.get("title") or ""
    desc = (card.get("description") or "").strip()
    return f"{title}\n\n{desc}".strip() if desc else title


async def process_card(
    deck: DeckClient,
    orch: OrchestratorClient,
    card: dict,
    *,
    board_id: int,
    todo_id: int,
    doing_id: int,
    done_id: int,
    mapping: dict[str, str],
    default: str,
) -> None:
    """Обработать одну карточку: claim -> агент -> комментарий -> Done."""
    card_id = card["id"]
    agent = agent_for_card(card, mapping, default)
    log.info("deck.card.start", card=card_id, agent=agent, title=card.get("title"))

    await deck.move_card(board_id, todo_id, card_id, doing_id)  # claim
    try:
        reply = await orch.chat(card_prompt(card), agent, f"deck:{card_id}")
        await deck.add_comment(card_id, f"🤖 {agent}:\n\n{reply or '(пустой ответ)'}")
        log.info("deck.card.done", card=card_id, agent=agent)
    except Exception as exc:  # noqa: BLE001 — одна карточка не должна валить цикл
        log.warning("deck.card.failed", card=card_id, agent=agent, error=str(exc))
        with contextlib.suppress(Exception):  # коммент не критичен для переноса в Done
            await deck.add_comment(card_id, f"❌ Не удалось выполнить: {exc}")
    await deck.move_card(board_id, doing_id, card_id, done_id)


async def run_once(deck: DeckClient, orch: OrchestratorClient) -> None:
    board = await deck.find_board(settings.deck_board)
    if board is None:
        log.warning("deck.board_missing", board=settings.deck_board)
        return
    stacks = await deck.stacks(board["id"])
    by_title = {s.get("title"): s for s in stacks}
    todo = by_title.get(settings.deck_todo_stack)
    doing = by_title.get(settings.deck_doing_stack)
    done = by_title.get(settings.deck_done_stack)
    if not (todo and doing and done):
        log.warning("deck.stacks_missing", have=list(by_title))
        return

    cards = todo.get("cards") or []
    if not cards:
        return
    mapping = settings.deck_label_agents
    log.info("deck.batch", count=len(cards))
    for card in cards:
        try:
            await process_card(
                deck,
                orch,
                card,
                board_id=board["id"],
                todo_id=todo["id"],
                doing_id=doing["id"],
                done_id=done["id"],
                mapping=mapping,
                default=settings.deck_default_agent,
            )
        except Exception as exc:  # noqa: BLE001 — продолжаем со следующей карточкой
            log.warning("deck.card.unhandled", card=card.get("id"), error=str(exc))


async def run() -> None:
    if not (settings.nextcloud_url and settings.nextcloud_user and settings.nextcloud_app_password):
        raise SystemExit("Не заданы NEXTCLOUD_URL/USER/APP_PASSWORD для Deck-worker")

    interval = settings.deck_poll_interval_min
    async with httpx.AsyncClient() as http:
        deck = DeckClient(
            http,
            settings.nextcloud_url,
            settings.nextcloud_user,
            settings.nextcloud_app_password,
        )
        orch = OrchestratorClient(http, settings.orchestrator_url)
        log.info("deck.start", board=settings.deck_board, interval_min=interval)
        while True:
            try:
                await run_once(deck, orch)
            except Exception as exc:  # noqa: BLE001 — цикл не должен падать
                log.warning("deck.cycle_failed", error=str(exc))
            if interval <= 0:
                return
            await asyncio.sleep(interval * 60)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

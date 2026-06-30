"""Deck-worker entrypoint.

Loop (or a single pass when deck_poll_interval_min=0):
    cards from To Do -> claim (In Progress) -> agent via the orchestrator ->
    comment with the result -> Done.

Claiming by moving to In Progress prevents the card from being processed again on
the next tick.
"""

from __future__ import annotations

import asyncio
import contextlib

import httpx
import structlog

from src.orchestrator.config import settings

from .client import DeckClient

log = structlog.get_logger()

_REPLY_TIMEOUT = 600  # an agent (especially recon with scans) may run for minutes


class OrchestratorClient:
    """Minimal client for the orchestrator (/chat)."""

    def __init__(self, http: httpx.AsyncClient, base_url: str) -> None:
        self._http = http
        self._base = base_url.rstrip("/")

    async def chat(self, message: str, agent: str, conversation_id: str) -> str:
        headers = {}
        if settings.orchestrator_api_token:
            headers["Authorization"] = f"Bearer {settings.orchestrator_api_token}"
        resp = await self._http.post(
            f"{self._base}/chat",
            json={"message": message, "agent": agent, "conversation_id": conversation_id},
            headers=headers,
            timeout=_REPLY_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json().get("reply", "")


def agent_for_card(card: dict, mapping: dict[str, str], default: str) -> str:
    """Pick an agent by the card's labels (first matching label), else default."""
    titles = {(label.get("title") or "").lower() for label in (card.get("labels") or [])}
    for label, agent in mapping.items():
        if label in titles:
            return agent
    return default


def card_prompt(card: dict) -> str:
    """Task text for the agent: title + description."""
    title = card.get("title") or ""
    desc = (card.get("description") or "").strip()
    return f"{title}\n\n{desc}".strip() if desc else title


async def process_card(
    deck: DeckClient,
    orch: OrchestratorClient,
    card: dict,
    *,
    board_id: int,
    doing_id: int,
    done_id: int,
    failed_id: int | None,
    mapping: dict[str, str],
    default: str,
) -> None:
    """Process a single card: claim -> agent -> comment -> Done/Failed.

    Success -> Done. Failure -> Failed (if the stack exists), otherwise the card
    stays in In Progress — it does NOT move to Done, so the board never reports a
    false success.
    """
    card_id = card["id"]
    agent = agent_for_card(card, mapping, default)
    log.info("deck.card.start", card=card_id, agent=agent, title=card.get("title"))

    await deck.move_card(board_id, card_id, doing_id)  # claim (In Progress)
    try:
        reply = await orch.chat(card_prompt(card), agent, f"deck:{card_id}")
        await deck.add_comment(card_id, f"🤖 {agent}:\n\n{reply or '(empty response)'}")
        log.info("deck.card.done", card=card_id, agent=agent)
        await deck.move_card(board_id, card_id, done_id)
    except Exception as exc:  # noqa: BLE001 — one card must not bring down the loop
        log.warning("deck.card.failed", card=card_id, agent=agent, error=str(exc))
        with contextlib.suppress(Exception):  # the comment is not critical for the move
            await deck.add_comment(card_id, f"❌ Execution failed: {exc}")
        if failed_id is not None:
            await deck.move_card(board_id, card_id, failed_id)
        else:  # no Failed stack — leave it in In Progress so the stall is visible
            log.warning("deck.no_failed_stack", card=card_id)


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
    # optional: if the stack is absent, a failure leaves the card in In Progress
    failed = by_title.get(settings.deck_failed_stack)
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
                doing_id=doing["id"],
                done_id=done["id"],
                failed_id=failed["id"] if failed else None,
                mapping=mapping,
                default=settings.deck_default_agent,
            )
        except Exception as exc:  # noqa: BLE001 — continue with the next card
            log.warning("deck.card.unhandled", card=card.get("id"), error=str(exc))


async def run() -> None:
    if not (settings.nextcloud_url and settings.nextcloud_user and settings.nextcloud_app_password):
        raise SystemExit("NEXTCLOUD_URL/USER/APP_PASSWORD are not set for the Deck-worker")

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
            except Exception as exc:  # noqa: BLE001 — the loop must not crash
                log.warning("deck.cycle_failed", error=str(exc))
            if interval <= 0:
                return
            await asyncio.sleep(interval * 60)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

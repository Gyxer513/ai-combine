"""Chronicle-worker — ДЕД ведёт летопись AI Combine.

Раз в день собирает «день»:
* комбайн: выполненные Deck-задачи (Done) + новые карточки-идеи;
* проекты Filipp: заметки Nextcloud, изменённые за окно (lookback).

Дайджест уходит ДЕДу (через оркестратор, agent=ded), его нарратив дописывается
в заметку «Летопись AI Combine» (новая запись — сверху, под датой).

Запуск: `python -m src.chronicle_worker.main`
(цикл при CHRONICLE_INTERVAL_MIN>0, иначе один проход).
"""

from __future__ import annotations

import asyncio
import time
from datetime import date

import httpx
import structlog

from src.deck_worker.client import DeckClient
from src.orchestrator.config import settings

from .notes import NotesClient

log = structlog.get_logger()


class OrchestratorClient:
    """Минимальный клиент к оркестратору (/chat)."""

    def __init__(self, http: httpx.AsyncClient, base_url: str) -> None:
        self._http = http
        self._base = base_url.rstrip("/")

    async def chat(self, message: str, agent: str, conversation_id: str) -> str:
        resp = await self._http.post(
            f"{self._base}/chat",
            json={"message": message, "agent": agent, "conversation_id": conversation_id},
            timeout=600,  # nemotron-ultra free может думать долго
        )
        resp.raise_for_status()
        return resp.json().get("reply", "")


def _recent(ts, cutoff: float) -> bool:
    return isinstance(ts, int | float) and ts >= cutoff


async def gather_combine(deck: DeckClient, cutoff: float) -> tuple[list[str], list[str]]:
    """(выполненные задачи комбайна, новые идеи) за окно."""
    done: list[str] = []
    ideas: list[str] = []
    tasks_board = await deck.find_board(settings.deck_board)
    if tasks_board:
        for stack in await deck.stacks(tasks_board["id"]):
            if stack.get("title") != settings.deck_done_stack:
                continue
            for card in stack.get("cards") or []:
                if _recent(card.get("lastModified"), cutoff):
                    done.append(card.get("title") or "")
    ideas_board = await deck.find_board(settings.research_board)
    if ideas_board:
        for stack in await deck.stacks(ideas_board["id"]):
            for card in stack.get("cards") or []:
                if _recent(card.get("createdAt"), cutoff):
                    ideas.append(card.get("title") or "")
    return [t for t in done if t], [t for t in ideas if t]


async def gather_projects(notes: NotesClient, cutoff: float) -> list[str]:
    """Заметки Filipp, изменённые за окно (кроме самой летописи)."""
    out: list[str] = []
    for note in await notes.list_notes():
        if note.get("title") == settings.chronicle_note:
            continue
        if _recent(note.get("modified"), cutoff):
            cat = note.get("category") or ""
            out.append(f"{note.get('title')}" + (f"  [{cat}]" if cat else ""))
    return out


def build_digest(done: list[str], ideas: list[str], notes: list[str]) -> str:
    """Сводка дня для ДЕДа."""

    def block(header: str, items: list[str]) -> str:
        body = "\n".join(f"- {i}" for i in items) if items else "- (ничего)"
        return f"{header}:\n{body}"

    return "\n\n".join(
        [
            block("Выполненные задачи комбайна (Deck → Done)", done),
            block("Новые идеи заработка", ideas),
            block("Изменённые заметки/проекты Filipp", notes),
        ]
    )


async def run_once(
    deck: DeckClient, notes: NotesClient, orch: OrchestratorClient
) -> dict[str, int]:
    cutoff = time.time() - settings.chronicle_lookback_hours * 3600
    done, ideas = await gather_combine(deck, cutoff)
    changed = await gather_projects(notes, cutoff)
    today = date.today().isoformat()

    digest = build_digest(done, ideas, changed)
    prompt = (
        f"Сводка за {today} (окно {settings.chronicle_lookback_hours} ч):\n\n{digest}\n\n"
        "Напиши запись летописи за этот день — короткий живой нарратив."
    )
    narrative = await orch.chat(prompt, settings.chronicle_agent, f"chronicle:{today}")
    await notes.append_section(
        title=settings.chronicle_note,
        category=settings.chronicle_note_category,
        heading=today,
        body=narrative or "(тихий день)",
    )
    stats = {"done": len(done), "ideas": len(ideas), "notes": len(changed)}
    log.info("chronicle.done", **stats)
    return stats


async def run() -> None:
    if not (settings.nextcloud_url and settings.nextcloud_user and settings.nextcloud_app_password):
        raise SystemExit("Не заданы NEXTCLOUD_URL/USER/APP_PASSWORD для chronicle-worker")

    interval = settings.chronicle_interval_min
    async with httpx.AsyncClient() as http:
        deck = DeckClient(
            http,
            settings.nextcloud_url,
            settings.nextcloud_user,
            settings.nextcloud_app_password,
        )
        notes = NotesClient(
            http,
            settings.nextcloud_url,
            settings.nextcloud_user,
            settings.nextcloud_app_password,
        )
        orch = OrchestratorClient(http, settings.orchestrator_url)
        log.info("chronicle.start", note=settings.chronicle_note, interval_min=interval)
        while True:
            try:
                await run_once(deck, notes, orch)
            except Exception as exc:  # noqa: BLE001 — цикл не должен падать
                log.warning("chronicle.cycle_failed", error=str(exc))
            if interval <= 0:
                return
            await asyncio.sleep(interval * 60)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

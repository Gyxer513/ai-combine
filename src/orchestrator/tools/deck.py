"""Инструмент планировщика: декомпозиция проекта в дочерние карточки Deck.

`register_planner_tool(agent)` навешивает `slice_project`: планировщик режет ТЗ на
подзадачи и раскладывает их карточками в стек «To Do» доски задач (с меткой
исполнителя), откуда их подхватывает deck-worker и отдаёт нужному агенту.

Метка ставится по реверсу `DECK_LABEL_AGENT_MAP` (agent -> label-title): для
маршрутизации на доске должны существовать те же метки (sec/code/ask). Если метки
нет — карточка создаётся без неё (deck-worker отдаст её агенту по умолчанию).
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from src.deck_worker.client import DeckClient

from ..config import settings

_KNOWN_AGENTS = {"recon", "coder", "assistant"}


class Subtask(BaseModel):
    """Одна дочерняя задача проекта."""

    title: str = Field(description="Краткий заголовок задачи (что сделать).")
    agent: str = Field(description="Исполнитель: recon | coder | assistant.")
    acceptance: str = Field(
        default="", description="Критерий приёмки: когда задача считается выполненной."
    )


async def plan_to_cards(project: str, subtasks: list[Subtask]) -> str:
    """Разложить подзадачи карточками в стек «To Do» доски задач (с метками).

    Вынесено из tool-обёртки, чтобы быть тестируемым отдельно от агента.
    """
    if not (
        settings.nextcloud_url
        and settings.nextcloud_user
        and settings.nextcloud_app_password
    ):
        return "Deck недоступен: не заданы NEXTCLOUD_URL/USER/APP_PASSWORD."
    if not subtasks:
        return "Не передано ни одной подзадачи — нечего раскладывать."

    unknown = sorted({s.agent.strip().lower() for s in subtasks} - _KNOWN_AGENTS)
    if unknown:
        return (
            f"Неизвестные исполнители: {', '.join(unknown)}. "
            "Допустимы: recon, coder, assistant."
        )

    # agent -> label-title (реверс DECK_LABEL_AGENT_MAP, который label -> agent)
    agent_to_label = {a: lbl for lbl, a in settings.deck_label_agents.items()}

    async with httpx.AsyncClient() as http:
        deck = DeckClient(
            http,
            settings.nextcloud_url,
            settings.nextcloud_user,
            settings.nextcloud_app_password,
        )
        board = await deck.find_board(settings.deck_board)
        if board is None:
            return f"Доска «{settings.deck_board}» не найдена."
        board_id = board["id"]
        stacks = await deck.stacks(board_id)
        todo = next(
            (s for s in stacks if s.get("title") == settings.deck_todo_stack), None
        )
        if todo is None:
            return f"Стек «{settings.deck_todo_stack}» не найден на доске."
        todo_id = todo["id"]
        labels_by_title = {
            (lbl.get("title") or "").lower(): lbl.get("id")
            for lbl in (board.get("labels") or [])
        }

        lines: list[str] = []
        for i, st in enumerate(subtasks):
            desc = (
                f"**Проект:** {project}\n\n"
                f"**Критерий приёмки:** {st.acceptance.strip() or '—'}"
            )
            card = await deck.create_card(board_id, todo_id, st.title, desc, order=i)
            card_id = card.get("id")
            label_title = agent_to_label.get(st.agent.strip().lower())
            label_id = labels_by_title.get((label_title or "").lower())
            tail = f" → {st.agent}"
            if card_id and label_id:
                try:
                    await deck.assign_label(board_id, todo_id, card_id, label_id)
                except httpx.HTTPError:
                    tail += " (метку не навесил — поставь вручную)"
            elif not label_id:
                tail += " (метки нет на доске — назначь вручную)"
            lines.append(f"• {st.title}{tail}")

    return f"Создал {len(lines)} карточек в «{settings.deck_todo_stack}»:\n" + "\n".join(
        lines
    )


def register_planner_tool(agent: Agent) -> None:
    """Навесить slice_project на агента-планировщика."""

    @agent.tool
    async def slice_project(ctx: RunContext, project: str, subtasks: list[Subtask]) -> str:
        """Разложить проект на дочерние задачи карточками на Deck-доске.

        Каждая подзадача становится карточкой в стеке «To Do» доски задач с меткой
        исполнителя — её подхватит автономный deck-worker. Возвращает сводку.

        Args:
            project: Короткое название/суть проекта (попадёт в описание карточек).
            subtasks: Список подзадач (заголовок + исполнитель + критерий приёмки).
        """
        return await plan_to_cards(project, subtasks)

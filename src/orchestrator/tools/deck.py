"""Planner tool: decompose a project into child Deck cards.

`register_planner_tool(agent)` attaches `slice_project`: the planner splits the
spec into subtasks and lays them out as cards in the "To Do" stack of the task
board (with an agent label), where deck-worker picks them up and hands them to the
right agent.

The label is set from the reverse of `DECK_LABEL_AGENT_MAP` (agent -> label-title):
the same labels (sec/code/ask) must exist on the board for routing. If a label is
missing, the card is created without it (deck-worker hands it to the default agent).
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from src.deck_worker.client import DeckClient

from ..config import settings

_KNOWN_AGENTS = {"recon", "coder", "assistant"}


class Subtask(BaseModel):
    """A single child task of the project."""

    title: str = Field(description="Short task title (what to do).")
    agent: str = Field(description="Executor: recon | coder | assistant.")
    acceptance: str = Field(
        default="", description="Acceptance criterion: when the task is considered done."
    )


async def plan_to_cards(project: str, subtasks: list[Subtask]) -> str:
    """Lay out subtasks as cards in the "To Do" stack of the task board (with labels).

    Extracted from the tool wrapper so it can be tested independently of the agent.
    """
    if not (
        settings.nextcloud_url
        and settings.nextcloud_user
        and settings.nextcloud_app_password
    ):
        return "Deck unavailable: NEXTCLOUD_URL/USER/APP_PASSWORD are not set."
    if not subtasks:
        return "No subtasks provided — nothing to lay out."

    unknown = sorted({s.agent.strip().lower() for s in subtasks} - _KNOWN_AGENTS)
    if unknown:
        return (
            f"Unknown executors: {', '.join(unknown)}. "
            "Allowed: recon, coder, assistant."
        )

    # agent -> label-title (reverse of DECK_LABEL_AGENT_MAP, which is label -> agent)
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
            return f"Board \"{settings.deck_board}\" not found."
        board_id = board["id"]
        stacks = await deck.stacks(board_id)
        todo = next(
            (s for s in stacks if s.get("title") == settings.deck_todo_stack), None
        )
        if todo is None:
            return f"Stack \"{settings.deck_todo_stack}\" not found on the board."
        todo_id = todo["id"]
        labels_by_title = {
            (lbl.get("title") or "").lower(): lbl.get("id")
            for lbl in (board.get("labels") or [])
        }

        lines: list[str] = []
        for i, st in enumerate(subtasks):
            desc = (
                f"**Project:** {project}\n\n"
                f"**Acceptance criterion:** {st.acceptance.strip() or '—'}"
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
                    tail += " (label not assigned — set it manually)"
            elif not label_id:
                tail += " (label not on the board — assign it manually)"
            lines.append(f"• {st.title}{tail}")

    return f"Created {len(lines)} cards in \"{settings.deck_todo_stack}\":\n" + "\n".join(
        lines
    )


def register_planner_tool(agent: Agent) -> None:
    """Attach slice_project to the planner agent."""

    @agent.tool
    async def slice_project(ctx: RunContext, project: str, subtasks: list[Subtask]) -> str:
        """Break a project into child tasks as cards on the Deck board.

        Each subtask becomes a card in the "To Do" stack of the task board with an
        agent label — the autonomous deck-worker picks it up. Returns a summary.

        Args:
            project: Short project name/gist (goes into the card descriptions).
            subtasks: List of subtasks (title + executor + acceptance criterion).
        """
        return await plan_to_cards(project, subtasks)

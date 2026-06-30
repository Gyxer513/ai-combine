"""Telegram bot handlers (one bot per agent).

Each bot is hard-bound to its agent by token — there is no switching, the bot
*is* the agent. Which agent is determined from `message.bot.token` via
`agent_by_token` (passed in from the polling data). Conversation history is keyed
`tg:<agent>:<chat_id>:<session>`; /reset increments the session.
"""

from __future__ import annotations

import asyncio
import contextlib

import structlog
from aiogram import Router
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from .orchestrator_client import OrchestratorClient

log = structlog.get_logger()
router = Router()

TG_LIMIT = 4096  # Telegram message length limit
DEFAULT_AGENT = "assistant"

TITLES = {
    "assistant": "💬 Assistant",
    "recon": "🛡 Recon",
    "coder": "🔨 Coder",
    "planner": "🧭 Planner",
}
BLURB = {
    "assistant": "general assistant: research, search, everyday questions",
    "recon": "information security: scanning and hardening your infra",
    "coder": "code and engineering: I write and review code, run tests",
    "planner": "planner: I break a project spec into tasks for the agents",
}

# Session number per (agent, chat) — for /reset. In-memory (history lives in the orchestrator).
_sessions: dict[tuple[str, int], int] = {}


def _agent_of(message: Message, agent_by_token: dict[str, str]) -> str:
    """The agent the bot that received the message is bound to."""
    token = getattr(message.bot, "token", "")
    return agent_by_token.get(token, DEFAULT_AGENT)


def _conversation_id(agent: str, chat_id: int) -> str:
    session = _sessions.get((agent, chat_id), 0)
    return f"tg:{agent}:{chat_id}:{session}"


async def _reply_chunked(message: Message, text: str) -> None:
    """Send the reply, split into chunks by the Telegram limit."""
    for i in range(0, len(text), TG_LIMIT):
        await message.answer(text[i : i + TG_LIMIT])


@router.message(CommandStart())
async def cmd_start(message: Message, agent_by_token: dict[str, str]) -> None:
    agent = _agent_of(message, agent_by_token)
    await message.answer(
        f"Hi! I'm {TITLES[agent]} — {BLURB[agent]}.\n\n"
        "Just type your question. /reset — start the conversation over, /who — who I am."
    )


@router.message(Command("help"))
async def cmd_help(message: Message, agent_by_token: dict[str, str]) -> None:
    agent = _agent_of(message, agent_by_token)
    await message.answer(
        f"This bot is {TITLES[agent]} ({BLURB[agent]}).\n"
        "Type your question as a normal message.\n"
        "/reset — forget the history and start over · /who — who I am."
    )


@router.message(Command("who"))
async def cmd_who(message: Message, agent_by_token: dict[str, str]) -> None:
    agent = _agent_of(message, agent_by_token)
    await message.answer(f"I'm {TITLES[agent]} — {BLURB[agent]}.")


@router.message(Command("reset"))
async def cmd_reset(message: Message, agent_by_token: dict[str, str]) -> None:
    agent = _agent_of(message, agent_by_token)
    _sessions[(agent, message.chat.id)] = _sessions.get((agent, message.chat.id), 0) + 1
    await message.answer("History cleared, starting over.")


async def _keep_typing(message: Message, chat_id: int) -> None:
    """Keep the "typing…" indicator alive while the agent works (it lasts ~5s)."""
    while True:
        with contextlib.suppress(Exception):
            await message.bot.send_chat_action(chat_id, ChatAction.TYPING)
        await asyncio.sleep(4)


@router.message()
async def on_text(
    message: Message,
    orchestrator: OrchestratorClient,
    agent_by_token: dict[str, str],
) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    chat_id = message.chat.id
    agent = _agent_of(message, agent_by_token)
    log.info("telegram.msg", chat=chat_id, agent=agent, text_len=len(text))
    typing = asyncio.create_task(_keep_typing(message, chat_id))
    try:
        reply = await orchestrator.chat(
            message=text, agent=agent, conversation_id=_conversation_id(agent, chat_id)
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("telegram.chat_failed", agent=agent, error=str(exc))
        await message.answer("Couldn't get a response — the orchestrator is unavailable.")
        return
    finally:
        typing.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await typing
    await _reply_chunked(message, reply or "(empty response)")

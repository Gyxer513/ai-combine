"""Хендлеры Telegram-бота (один бот на агента).

Каждый бот жёстко привязан к своему агенту по токену — переключения нет, бот
*и есть* агент. Какой агент, определяется по `message.bot.token` через
`agent_by_token` (прокидывается из polling-данных). История диалога —
`tg:<agent>:<chat_id>:<session>`; /reset инкрементит session.
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

TG_LIMIT = 4096  # лимит длины сообщения Telegram
DEFAULT_AGENT = "kolobok"

TITLES = {
    "kolobok": "🍞 Колобок",
    "koschei": "🦴 Кощей",
    "levsha": "🔨 Левша",
    "ded": "👴 Дед",
}
BLURB = {
    "kolobok": "общий помощник: ресёрч, поиск, бытовые вопросы",
    "koschei": "информационная безопасность: скан и хардненинг твоей инфры",
    "levsha": "код и инженерия: пишу и ревьюю код, гоняю тесты",
    "ded": "летописец: хроника комбайна и проектов, пересказ событий",
}

# Номер сессии по (агент, чат) — для /reset. In-memory (история — в оркестраторе).
_sessions: dict[tuple[str, int], int] = {}


def _agent_of(message: Message, agent_by_token: dict[str, str]) -> str:
    """Агент, к которому привязан бот, получивший сообщение."""
    token = getattr(message.bot, "token", "")
    return agent_by_token.get(token, DEFAULT_AGENT)


def _conversation_id(agent: str, chat_id: int) -> str:
    session = _sessions.get((agent, chat_id), 0)
    return f"tg:{agent}:{chat_id}:{session}"


async def _reply_chunked(message: Message, text: str) -> None:
    """Отправить ответ, разбив на куски по лимиту Telegram."""
    for i in range(0, len(text), TG_LIMIT):
        await message.answer(text[i : i + TG_LIMIT])


@router.message(CommandStart())
async def cmd_start(message: Message, agent_by_token: dict[str, str]) -> None:
    agent = _agent_of(message, agent_by_token)
    await message.answer(
        f"Привет! Я {TITLES[agent]} — {BLURB[agent]}.\n\n"
        "Просто пиши вопрос. /reset — начать диалог заново, /who — кто я."
    )


@router.message(Command("help"))
async def cmd_help(message: Message, agent_by_token: dict[str, str]) -> None:
    agent = _agent_of(message, agent_by_token)
    await message.answer(
        f"Этот бот — {TITLES[agent]} ({BLURB[agent]}).\n"
        "Пиши вопрос обычным сообщением.\n"
        "/reset — забыть историю и начать заново · /who — кто я."
    )


@router.message(Command("who"))
async def cmd_who(message: Message, agent_by_token: dict[str, str]) -> None:
    agent = _agent_of(message, agent_by_token)
    await message.answer(f"Я {TITLES[agent]} — {BLURB[agent]}.")


@router.message(Command("reset"))
async def cmd_reset(message: Message, agent_by_token: dict[str, str]) -> None:
    agent = _agent_of(message, agent_by_token)
    _sessions[(agent, message.chat.id)] = _sessions.get((agent, message.chat.id), 0) + 1
    await message.answer("История забыта, начинаем заново.")


async def _keep_typing(message: Message, chat_id: int) -> None:
    """Держать индикатор «печатает…» пока агент работает (он живёт ~5с)."""
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
        await message.answer("Не получилось получить ответ — оркестратор недоступен.")
        return
    finally:
        typing.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await typing
    await _reply_chunked(message, reply or "(пустой ответ)")

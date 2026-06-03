"""Хендлеры Telegram-бота.

Команды переключают активного агента в чате; обычный текст уходит выбранному
агенту через оркестратор. История диалога связывается по conversation_id
`tg:<chat_id>:<session>`; /reset инкрементит session и начинает диалог заново.
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

# Команда/алиас -> агент.
AGENT_BY_COMMAND = {
    "kolobok": "kolobok",
    "ask": "kolobok",
    "koschei": "koschei",
    "sec": "koschei",
    "levsha": "levsha",
    "code": "levsha",
}
TITLES = {"kolobok": "🍞 Колобок", "koschei": "🦴 Кощей", "levsha": "🔨 Левша"}
DEFAULT_AGENT = "kolobok"

# Состояние по чату: активный агент + номер сессии (для /reset). In-memory.
_state: dict[int, dict] = {}


def _chat_state(chat_id: int) -> dict:
    return _state.setdefault(chat_id, {"agent": DEFAULT_AGENT, "session": 0})


def _conversation_id(chat_id: int) -> str:
    st = _chat_state(chat_id)
    return f"tg:{chat_id}:{st['session']}"


async def _reply_chunked(message: Message, text: str) -> None:
    """Отправить ответ, разбив на куски по лимиту Telegram."""
    for i in range(0, len(text), TG_LIMIT):
        await message.answer(text[i : i + TG_LIMIT])


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Я — мост к трём агентам AI Combine.\n\n"
        "🍞 /kolobok (/ask) — общий помощник и ресёрч\n"
        "🦴 /koschei (/sec) — информационная безопасность\n"
        "🔨 /levsha (/code) — код и инженерия\n\n"
        "Выбери агента командой и просто пиши сообщения.\n"
        "/who — кто активен · /reset — начать диалог заново · /help — помощь"
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Команды:\n"
        "/kolobok /koschei /levsha — переключить агента (алиасы /ask /sec /code)\n"
        "/who — показать активного агента\n"
        "/reset — забыть историю и начать заново\n\n"
        "Каждый агент ищет по своей базе знаний и умеет web_search."
    )


@router.message(Command(*AGENT_BY_COMMAND.keys()))
async def cmd_switch_agent(message: Message) -> None:
    command = (message.text or "")[1:].split("@")[0].split()[0].lower()
    agent = AGENT_BY_COMMAND.get(command, DEFAULT_AGENT)
    _chat_state(message.chat.id)["agent"] = agent
    await message.answer(f"Активен {TITLES[agent]}. Пиши вопрос.")


@router.message(Command("who"))
async def cmd_who(message: Message) -> None:
    agent = _chat_state(message.chat.id)["agent"]
    await message.answer(f"Сейчас отвечает {TITLES[agent]}.")


@router.message(Command("reset"))
async def cmd_reset(message: Message) -> None:
    _chat_state(message.chat.id)["session"] += 1
    await message.answer("История забыта, начинаем заново.")


async def _keep_typing(message: Message, chat_id: int) -> None:
    """Держать индикатор «печатает…» пока агент работает (он живёт ~5с)."""
    while True:
        with contextlib.suppress(Exception):
            await message.bot.send_chat_action(chat_id, ChatAction.TYPING)
        await asyncio.sleep(4)


@router.message()
async def on_text(message: Message, orchestrator: OrchestratorClient) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    chat_id = message.chat.id
    agent = _chat_state(chat_id)["agent"]
    typing = asyncio.create_task(_keep_typing(message, chat_id))
    try:
        reply = await orchestrator.chat(
            message=text, agent=agent, conversation_id=_conversation_id(chat_id)
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("telegram.chat_failed", error=str(exc))
        await message.answer("Не получилось получить ответ — оркестратор недоступен.")
        return
    finally:
        typing.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await typing
    await _reply_chunked(message, reply or "(пустой ответ)")

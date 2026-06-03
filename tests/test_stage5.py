"""Тесты Этапа 5 (Telegram): whitelist и маппинг команд."""

from __future__ import annotations

from aiogram.types import User

from src.telegram_bot import handlers
from src.telegram_bot.middleware import WhitelistMiddleware


def _user(uid: int) -> User:
    return User(id=uid, is_bot=False, first_name="t")


async def _run_mw(allowed: set[int], uid: int, *, allow_bootstrap: bool = False) -> bool:
    """True, если хендлер был вызван (доступ разрешён)."""
    mw = WhitelistMiddleware(allowed, allow_bootstrap=allow_bootstrap)
    called = {"v": False}

    async def handler(event, data):
        called["v"] = True
        return "ok"

    await mw(handler, object(), {"event_from_user": _user(uid)})
    return called["v"]


async def test_whitelist_allows_listed():
    assert await _run_mw({123, 456}, 123) is True


async def test_whitelist_blocks_unlisted():
    assert await _run_mw({123}, 999) is False


async def test_whitelist_empty_is_fail_closed_by_default():
    # пустой whitelist без bootstrap -> никого не пускаем
    assert await _run_mw(set(), 999) is False


async def test_whitelist_empty_bootstrap_allows():
    # явный bootstrap-режим (дев) -> пускаем
    assert await _run_mw(set(), 999, allow_bootstrap=True) is True


def test_command_aliases_map_to_agents():
    assert handlers.AGENT_BY_COMMAND["sec"] == "koschei"
    assert handlers.AGENT_BY_COMMAND["code"] == "levsha"
    assert handlers.AGENT_BY_COMMAND["ask"] == "kolobok"


def test_conversation_id_changes_after_reset():
    handlers._state.clear()
    cid1 = handlers._conversation_id(42)
    handlers._chat_state(42)["session"] += 1  # эмулируем /reset
    cid2 = handlers._conversation_id(42)
    assert cid1 != cid2
    assert cid1.startswith("tg:42:")

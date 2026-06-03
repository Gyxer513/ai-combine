"""Тесты Этапа 5 (Telegram): whitelist, маппинг ботов на агентов, conversation_id."""

from __future__ import annotations

from aiogram.types import User

from src.orchestrator.config import Settings
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


def test_agent_bot_tokens_mapping():
    # общий токен -> Колобок; отдельные -> свои агенты; пустые не попадают
    s = Settings(
        telegram_bot_token="A",
        telegram_bot_token_koschei="B",
        telegram_bot_token_levsha="",
    )
    assert s.agent_bot_tokens == {"kolobok": "A", "koschei": "B"}


def test_agent_bot_token_kolobok_overrides_common():
    s = Settings(telegram_bot_token="common", telegram_bot_token_kolobok="explicit")
    assert s.agent_bot_tokens["kolobok"] == "explicit"


def test_conversation_id_changes_after_reset():
    handlers._sessions.clear()
    cid1 = handlers._conversation_id("koschei", 42)
    handlers._sessions[("koschei", 42)] = 1  # эмулируем /reset
    cid2 = handlers._conversation_id("koschei", 42)
    assert cid1 != cid2
    assert cid1.startswith("tg:koschei:42:")


def test_conversation_id_isolated_per_agent():
    handlers._sessions.clear()
    # один и тот же chat_id у разных ботов -> разные диалоги
    assert handlers._conversation_id("kolobok", 7) != handlers._conversation_id("levsha", 7)

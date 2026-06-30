"""Whitelist access to the bot.

`TELEGRAM_ALLOWED_USERS` — a comma-separated list of user_ids. Messages from anyone
else are silently ignored.

An empty whitelist is **fail-closed** by default: no one is let in, and denied ids are
logged (WARNING) so the owner can learn their id and add it to the whitelist.
The open bootstrap mode (let everyone in when the list is empty) is enabled only by an
explicit `TELEGRAM_ALLOW_BOOTSTRAP=true` — for local development, not for a prod deploy.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

log = structlog.get_logger()


class WhitelistMiddleware(BaseMiddleware):
    """Lets through only allowed users."""

    def __init__(self, allowed: set[int], *, allow_bootstrap: bool = False) -> None:
        self._allowed = allowed
        self._allow_bootstrap = allow_bootstrap

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")

        if not self._allowed:
            if self._allow_bootstrap:
                if user:
                    log.warning("telegram.whitelist_empty_bootstrap", user_id=user.id)
                return await handler(event, data)
            # fail-closed: empty and no bootstrap — no one. Log the id so it can be added.
            if user:
                log.warning("telegram.denied_whitelist_empty", user_id=user.id)
            return None

        if user and user.id in self._allowed:
            return await handler(event, data)

        if user:
            log.info("telegram.denied", user_id=user.id)
        return None  # silently ignore

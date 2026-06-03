"""Whitelist-доступ к боту.

`TELEGRAM_ALLOWED_USERS` — список user_id через запятую. Чужие сообщения молча
игнорируются.

Пустой whitelist по умолчанию **fail-closed**: никого не пускаем, а id отказанных
пишем в лог (WARNING) — чтобы владелец узнал свой id и добавил его в whitelist.
Открытый bootstrap-режим (пускать всех при пустом списке) включается только явным
`TELEGRAM_ALLOW_BOOTSTRAP=true` — для локальной разработки, не для прод-деплоя.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

log = structlog.get_logger()


class WhitelistMiddleware(BaseMiddleware):
    """Пропускает только разрешённых пользователей."""

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
            # fail-closed: пусто и без bootstrap — никого. Логируем id для добавления.
            if user:
                log.warning("telegram.denied_whitelist_empty", user_id=user.id)
            return None

        if user and user.id in self._allowed:
            return await handler(event, data)

        if user:
            log.info("telegram.denied", user_id=user.id)
        return None  # молча игнорируем

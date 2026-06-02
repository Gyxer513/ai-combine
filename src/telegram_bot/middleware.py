"""Whitelist-доступ к боту.

`TELEGRAM_ALLOWED_USERS` — список user_id через запятую. Чужие сообщения молча
игнорируются. Если whitelist пуст (не настроен) — bootstrap-режим: пускаем всех,
но пишем в лог предупреждение (чтобы владелец узнал свой id и закрыл доступ).
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

    def __init__(self, allowed: set[int]) -> None:
        self._allowed = allowed

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")

        if not self._allowed:
            if user:
                log.warning("telegram.whitelist_empty", user_id=user.id)
            return await handler(event, data)

        if user and user.id in self._allowed:
            return await handler(event, data)

        if user:
            log.info("telegram.denied", user_id=user.id)
        return None  # молча игнорируем

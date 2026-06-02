"""Entrypoint Telegram-бота (aiogram 3, long polling).

Запуск:
    uv run python -m src.telegram_bot.main

Бот сам по себе не зовёт LLM — он мост к оркестратору (/chat). Доступ ограничен
whitelist'ом (TELEGRAM_ALLOWED_USERS).
"""

from __future__ import annotations

import asyncio

import httpx
import structlog
from aiogram import Bot, Dispatcher

from src.orchestrator.config import settings

from .handlers import router
from .middleware import WhitelistMiddleware
from .orchestrator_client import OrchestratorClient

log = structlog.get_logger()


async def run() -> None:
    if not settings.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN не задан в .env")

    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()
    dp.message.middleware(WhitelistMiddleware(settings.allowed_user_ids))
    dp.include_router(router)

    async with httpx.AsyncClient() as http:
        orchestrator = OrchestratorClient(http, settings.orchestrator_url)
        log.info(
            "telegram.start",
            allowed=len(settings.allowed_user_ids) or "ALL (bootstrap)",
            orchestrator=settings.orchestrator_url,
        )
        await dp.start_polling(bot, orchestrator=orchestrator)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

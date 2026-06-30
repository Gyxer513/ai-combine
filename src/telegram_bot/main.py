"""Entrypoint Telegram-бота (aiogram 3, long polling).

Запуск:
    uv run python -m src.telegram_bot.main

Бот сам по себе не зовёт LLM — он мост к оркестратору (/chat). Доступ ограничен
whitelist'ом (TELEGRAM_ALLOWED_USERS).
"""

from __future__ import annotations

import asyncio
import logging

import httpx
import structlog
from aiogram import Bot, Dispatcher

from src.orchestrator.config import settings

from .handlers import router
from .middleware import WhitelistMiddleware
from .orchestrator_client import OrchestratorClient

log = structlog.get_logger()


async def run() -> None:
    # aiogram пишет ошибки роутинга/хендлеров через стандартный logging —
    # без этого они уходят в никуда, и сбои выглядят как «бот молчит».
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    tokens = settings.agent_bot_tokens  # {agent: token}
    if not tokens:
        raise SystemExit(
            "Не задан ни один токен бота "
            "(TELEGRAM_BOT_TOKEN / TELEGRAM_BOT_TOKEN_ASSISTANT/RECON/CODER/PLANNER)"
        )

    bots = []
    agent_by_token: dict[str, str] = {}
    for agent, token in tokens.items():
        bots.append(Bot(token=token))
        agent_by_token[token] = agent

    dp = Dispatcher()
    dp.message.middleware(
        WhitelistMiddleware(
            settings.allowed_user_ids,
            allow_bootstrap=settings.telegram_allow_bootstrap,
        )
    )
    dp.include_router(router)

    if not settings.allowed_user_ids:
        mode = "ALL (bootstrap)" if settings.telegram_allow_bootstrap else "NONE (fail-closed)"
    else:
        mode = str(len(settings.allowed_user_ids))

    async with httpx.AsyncClient() as http:
        orchestrator = OrchestratorClient(http, settings.orchestrator_url)
        log.info(
            "telegram.start",
            bots=list(tokens.keys()),
            allowed=mode,
            orchestrator=settings.orchestrator_url,
        )
        await dp.start_polling(
            *bots, orchestrator=orchestrator, agent_by_token=agent_by_token
        )


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

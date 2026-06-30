"""Telegram bot entrypoint (aiogram 3, long polling).

Run:
    uv run python -m src.telegram_bot.main

The bot does not call the LLM itself — it's a bridge to the orchestrator (/chat).
Access is restricted by a whitelist (TELEGRAM_ALLOWED_USERS).
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
    # aiogram logs routing/handler errors through the standard logging module —
    # without this they go nowhere and failures just look like "the bot is silent".
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    tokens = settings.agent_bot_tokens  # {agent: token}
    if not tokens:
        raise SystemExit(
            "No bot token is set "
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

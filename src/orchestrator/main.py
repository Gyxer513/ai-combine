"""FastAPI entrypoint оркестратора.

Этап 1: только health-check и проверка связи с LiteLLM.
Этап 2+: подключаются агенты и /chat (см. api/routes.py).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI

from .config import settings

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=30)
    log.info("orchestrator.start", litellm=settings.litellm_base_url)
    try:
        yield
    finally:
        await app.state.http.aclose()
        log.info("orchestrator.stop")


app = FastAPI(title="AI Combine Orchestrator", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/litellm")
async def health_litellm() -> dict[str, object]:
    """Проверка, что прокси отвечает и отдаёт список моделей."""
    url = f"{settings.litellm_base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {settings.litellm_master_key}"}
    try:
        resp = await app.state.http.get(url, headers=headers)
        resp.raise_for_status()
        models = [m.get("id") for m in resp.json().get("data", [])]
        return {"status": "ok", "models": models}
    except httpx.HTTPError as exc:
        return {"status": "error", "detail": str(exc)}


# Этап 2: app.include_router(routes.router)

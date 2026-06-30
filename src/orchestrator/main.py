"""FastAPI entrypoint for the orchestrator.

Stage 1: health-check and LiteLLM connectivity check.
Stage 2: agents and /chat + OpenAI-compatible /v1 (see api/routes.py).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI

from .api import dashboard, routes
from .config import settings

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=30)
    if not settings.orchestrator_api_token:
        log.warning(
            "orchestrator.no_api_token",
            msg="ORCHESTRATOR_API_TOKEN is not set — /chat and /v1/* run without auth; "
            "relying on bind localhost alone. Set a token for production.",
        )
    log.info("orchestrator.start", litellm=settings.litellm_base_url)
    try:
        yield
    finally:
        await app.state.http.aclose()
        log.info("orchestrator.stop")


app = FastAPI(title="AI Combine Orchestrator", version="0.1.0", lifespan=lifespan)
app.include_router(routes.router)
app.include_router(dashboard.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/litellm")
async def health_litellm() -> dict[str, object]:
    """Check that the proxy responds and returns a model list."""
    url = f"{settings.litellm_base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {settings.litellm_master_key}"}
    try:
        resp = await app.state.http.get(url, headers=headers)
        resp.raise_for_status()
        models = [m.get("id") for m in resp.json().get("data", [])]
        return {"status": "ok", "models": models}
    except httpx.HTTPError as exc:
        return {"status": "error", "detail": str(exc)}

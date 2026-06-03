# syntax=docker/dockerfile:1
# deck-worker — автономное выполнение задач из Nextcloud Deck.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Только базовые зависимости (httpx, structlog, pydantic) — без rag/telegram.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-install-project

COPY src/ ./src/

ENV PATH="/app/.venv/bin:$PATH"
# Цикл при DECK_POLL_INTERVAL_MIN>0, иначе один проход.
CMD ["python", "-m", "src.deck_worker.main"]

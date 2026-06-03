# syntax=docker/dockerfile:1
# sandbox-broker — единственный сервис с доступом к docker.sock.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Только базовые зависимости (fastapi, docker, structlog) — без rag/telegram.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-install-project

COPY src/ ./src/

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 9000
CMD ["uvicorn", "src.sandbox_broker.main:app", "--host", "0.0.0.0", "--port", "9000"]

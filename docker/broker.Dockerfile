# syntax=docker/dockerfile:1
# sandbox-broker — the only service with access to docker.sock.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Only the base dependencies (fastapi, docker, structlog) — without rag/telegram.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-install-project

COPY src/ ./src/

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 9000
CMD ["uvicorn", "src.sandbox_broker.main:app", "--host", "0.0.0.0", "--port", "9000"]

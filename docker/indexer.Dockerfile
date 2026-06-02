# syntax=docker/dockerfile:1
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-install-project --extra rag

COPY src/ ./src/

ENV PATH="/app/.venv/bin:$PATH"
# Этап 3: прогон индексатора. RAG_INDEX_INTERVAL_MIN>0 -> цикл, иначе один проход.
CMD ["python", "-m", "src.rag_indexer.main"]

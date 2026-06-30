# syntax=docker/dockerfile:1
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Dependencies (cacheable layer).
#   --extra rag:  the orchestrator imports qdrant_client.
#   --extra docs: local docs semantic search (onnxruntime/faiss) — needed at QUERY time
#                 to embed; the model itself downloads lazily into the data volume.
#                 Drop it if DOCS_SEARCH_ENABLED stays false to slim the image.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-install-project --extra rag --extra docs

COPY src/ ./src/

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "src.orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000"]

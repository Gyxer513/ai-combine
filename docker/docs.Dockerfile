# syntax=docker/dockerfile:1
# One-off builder for the docs semantic index: chunks the Markdown corpus, embeds it
# with EmbeddingGemma (ONNX), and writes the FAISS index to the shared data volume.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-install-project --extra docs

COPY src/ ./src/
# The corpus (DOCS_GLOBS): the combine's own Markdown.
COPY README.md README.ru.md SECURITY.md ./
COPY docs/ ./docs/

ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "-m", "src.docs_search.index"]

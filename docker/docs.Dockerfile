# syntax=docker/dockerfile:1
# One-off builder for the docs semantic index. Two steps, both runnable from this image:
#   convert: docs (PDF/DOCX/...) in data/docs_in -> Markdown in data/docs_corpus
#   index:   chunk the Markdown corpus, embed with EmbeddingGemma (ONNX) -> FAISS index
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-install-project --extra docs --extra convert

COPY src/ ./src/
# The corpus (DOCS_GLOBS): the combine's own Markdown.
COPY README.md README.ru.md SECURITY.md ./
COPY docs/ ./docs/

ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "-m", "src.docs_search.index"]

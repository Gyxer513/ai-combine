"""Разбиение текста на чанки фиксированного размера с перекрытием.

Размер считается в токенах (tiktoken `cl100k_base` как универсальный счётчик).
Перекрытие сохраняет контекст на границах чанков.
"""

from __future__ import annotations

import tiktoken

from src.orchestrator.config import settings

_enc = tiktoken.get_encoding("cl100k_base")


def chunk_text(
    text: str, *, max_tokens: int | None = None, overlap: int | None = None
) -> list[str]:
    """Разбить текст на чанки ~max_tokens токенов с перекрытием overlap."""
    max_tokens = max_tokens or settings.rag_chunk_tokens
    overlap = overlap or settings.rag_chunk_overlap
    tokens = _enc.encode(text)
    if not tokens:
        return []

    step = max(1, max_tokens - overlap)
    chunks: list[str] = []
    for start in range(0, len(tokens), step):
        window = tokens[start : start + max_tokens]
        piece = _enc.decode(window).strip()
        if piece:
            chunks.append(piece)
        if start + max_tokens >= len(tokens):
            break
    return chunks

"""Split text into fixed-size chunks with overlap.

Size is measured in tokens (tiktoken `cl100k_base` as a universal counter).
The overlap preserves context across chunk boundaries.
"""

from __future__ import annotations

import tiktoken

from src.orchestrator.config import settings

_enc = tiktoken.get_encoding("cl100k_base")


def chunk_text(
    text: str, *, max_tokens: int | None = None, overlap: int | None = None
) -> list[str]:
    """Split text into chunks of ~max_tokens tokens with an overlap of `overlap`."""
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

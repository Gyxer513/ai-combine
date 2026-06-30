"""Markdown-aware chunking for the docs index.

Splits a document along headings, then windows each section into ~`chunk_chars`-sized
pieces with overlap. Each chunk carries its source path and the heading trail it lives
under, so search results can cite "file > Section > Subsection".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass(frozen=True, slots=True)
class Chunk:
    """One indexable piece of a document."""

    text: str
    source: str  # repo-relative path
    heading: str  # heading trail, e.g. "Security > Secrets"


def _heading_trail(stack: list[tuple[int, str]]) -> str:
    return " > ".join(title for _, title in stack)


def _split_section(body: str, chunk_chars: int, overlap: int) -> list[str]:
    """Window a section body into char-bounded pieces, breaking on blank lines first."""
    body = body.strip()
    if not body:
        return []
    if len(body) <= chunk_chars:
        return [body]
    # Prefer paragraph boundaries; fall back to a hard window with overlap.
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    chunks: list[str] = []
    cur = ""
    for p in paras:
        if len(p) > chunk_chars:  # a single huge paragraph — hard-window it
            if cur:
                chunks.append(cur)
                cur = ""
            start = 0
            while start < len(p):
                chunks.append(p[start : start + chunk_chars])
                start += max(1, chunk_chars - overlap)
            continue
        if len(cur) + len(p) + 2 > chunk_chars:
            if cur:
                chunks.append(cur)
            cur = p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        chunks.append(cur)
    return chunks


def markdown_chunks(text: str, source: str, *, chunk_chars: int, overlap: int) -> list[Chunk]:
    """Split a Markdown document into heading-aware chunks."""
    lines = text.splitlines()
    stack: list[tuple[int, str]] = []  # (level, title)
    body: list[str] = []
    out: list[Chunk] = []

    def flush() -> None:
        section = "\n".join(body).strip()
        for piece in _split_section(section, chunk_chars, overlap):
            out.append(Chunk(text=piece, source=source, heading=_heading_trail(stack)))
        body.clear()

    for line in lines:
        m = _HEADING.match(line)
        if m:
            flush()  # close the previous section before changing heading context
            level = len(m.group(1))
            title = m.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
        else:
            body.append(line)
    flush()
    return out

"""Build the docs semantic index, or self-test the embedder.

    python -m src.docs_search.index            # build the index from repo Markdown
    python -m src.docs_search.index --selftest # load the model and sanity-check it

Discovers Markdown files via DOCS_GLOBS (relative to the repo root / cwd), chunks them,
embeds with EmbeddingGemma (ONNX), and writes a FAISS index + metadata to
DOCS_INDEX_DIR. The orchestrator only reads that prebuilt index at query time.
"""

from __future__ import annotations

import sys
from pathlib import Path

import structlog

from src.orchestrator.config import settings

from .chunker import markdown_chunks
from .embedder import DocsEmbedder
from .store import save_index

log = structlog.get_logger()


def discover(root: str) -> list[Path]:
    """All Markdown files matching DOCS_GLOBS, de-duplicated and sorted."""
    base = Path(root)
    seen: set[Path] = set()
    for pattern in settings.docs_globs.split(","):
        pattern = pattern.strip()
        if not pattern:
            continue
        for p in base.glob(pattern):
            if p.is_file():
                seen.add(p.resolve())
    return sorted(seen)


def build(root: str = ".") -> int:
    """Build the index from the docs corpus. Returns the number of chunks indexed."""
    files = discover(root)
    if not files:
        log.warning("docs.no_files", globs=settings.docs_globs, root=root)
        return 0

    base = Path(root).resolve()
    chunks = []
    for f in files:
        rel = f.relative_to(base).as_posix() if f.is_relative_to(base) else f.name
        text = f.read_text(encoding="utf-8", errors="replace")
        chunks.extend(
            markdown_chunks(
                text, rel,
                chunk_chars=settings.docs_chunk_chars,
                overlap=settings.docs_chunk_overlap,
            )
        )
    if not chunks:
        log.warning("docs.no_chunks", files=len(files))
        return 0

    embedder = DocsEmbedder()
    vectors = _embed_all(embedder, [c.text for c in chunks])
    meta = [{"text": c.text, "source": c.source, "heading": c.heading} for c in chunks]
    save_index(settings.docs_index_dir, vectors, meta)
    log.info("docs.indexed", files=len(files), chunks=len(chunks), dir=settings.docs_index_dir)
    return len(chunks)


def _embed_all(embedder: DocsEmbedder, texts: list[str], batch: int = 32):
    import numpy as np

    out = []
    for i in range(0, len(texts), batch):
        out.append(embedder.embed(texts[i : i + batch], kind="document"))
        log.info("docs.embed_batch", done=min(i + batch, len(texts)), total=len(texts))
    return np.vstack(out)


def selftest() -> int:
    """Load the model and check that a relevant doc scores above an unrelated one."""

    embedder = DocsEmbedder()
    q = embedder.embed_one("how is the sandbox isolated?", kind="query")
    docs = embedder.embed(
        [
            "The sandbox-broker is the only service with docker.sock; sandboxes are ephemeral.",
            "Bananas are a good source of potassium.",
        ],
        kind="document",
    )
    sims = docs @ q
    rel, unrel = float(sims[0]), float(sims[1])
    log.info("docs.selftest", dim=int(q.shape[0]), relevant=rel, unrelated=unrel)
    ok = rel > unrel
    print(f"dim={q.shape[0]} relevant={rel:.3f} unrelated={unrel:.3f} -> {'OK' if ok else 'FAIL'}")
    return 0 if ok else 1


def main() -> None:
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    build(".")


if __name__ == "__main__":
    main()

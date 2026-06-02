"""Индексатор RAG: Nextcloud (Notes + WebDAV) → чанки → embed (API) → Qdrant.

Запуск:
    uv run python -m src.rag_indexer.main

Манифест `data/rag_manifest.json` хранит хэши документов — неизменённые
пропускаются, чтобы не гонять embedding API повторно (важно при платном API).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import structlog

from src.orchestrator.rag.embedder import EmbeddingClient
from src.orchestrator.rag.store import VectorStore, point_id

from .base import RagDocument
from .chunker import chunk_text
from .sources.notes import fetch_notes
from .sources.webdav import fetch_webdav

log = structlog.get_logger()

MANIFEST = Path("data/rag_manifest.json")
EMBED_BATCH = 10  # лимит батча text-embedding-v4


async def _embed_all(embedder: EmbeddingClient, chunks: list[str]) -> list[list[float]]:
    """Эмбеддить чанки батчами."""
    vectors: list[list[float]] = []
    for i in range(0, len(chunks), EMBED_BATCH):
        vectors.extend(await embedder.embed(chunks[i : i + EMBED_BATCH]))
    return vectors


async def index_document(
    doc: RagDocument, embedder: EmbeddingClient, store: VectorStore, manifest: dict[str, str]
) -> int:
    """Проиндексировать документ. Возврат: число записанных чанков (0 если скип)."""
    content_hash = doc.content_hash()
    if manifest.get(doc.doc_id) == content_hash:
        return 0

    chunks = chunk_text(doc.text)
    if not chunks:
        return 0

    vectors = await _embed_all(embedder, chunks)
    points: list[tuple[str, list[float], dict]] = []
    for i, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
        points.append(
            (
                point_id(doc.doc_id, i),
                vector,
                {
                    "doc_id": doc.doc_id,
                    "namespace": doc.namespace,
                    "source": doc.source,
                    "path": doc.path,
                    "modified": doc.modified,
                    "chunk_index": i,
                    "text": chunk,
                    "hash": content_hash,
                },
            )
        )

    await store.delete_doc(doc.namespace, doc.doc_id)
    await store.upsert(doc.namespace, points)
    manifest[doc.doc_id] = content_hash
    return len(chunks)


async def run(manifest: dict[str, str]) -> dict[str, int]:
    """Один проход индексации. Мутирует `manifest`, возвращает статистику."""
    store = VectorStore()
    stats = {"docs": 0, "indexed": 0, "skipped": 0, "chunks": 0}
    try:
        async with httpx.AsyncClient() as http:
            embedder = EmbeddingClient(http)
            docs = await fetch_notes(http) + await fetch_webdav()
            stats["docs"] = len(docs)
            for doc in docs:
                written = await index_document(doc, embedder, store, manifest)
                if written:
                    stats["indexed"] += 1
                    stats["chunks"] += written
                else:
                    stats["skipped"] += 1
    finally:
        await store.close()

    log.info("indexer.done", **stats)
    return stats


def _load_manifest() -> dict[str, str]:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {}


def _save_manifest(manifest: dict[str, str]) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    manifest = _load_manifest()
    stats = asyncio.run(run(manifest))
    _save_manifest(manifest)
    print(
        f"Готово: документов {stats['docs']}, "
        f"проиндексировано {stats['indexed']}, пропущено {stats['skipped']}, "
        f"чанков записано {stats['chunks']}."
    )


if __name__ == "__main__":
    main()

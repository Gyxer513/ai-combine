"""FAISS-backed store for the docs index: persist and query.

A flat inner-product index over L2-normalized vectors (= cosine similarity). The corpus
is small (the combine's own docs), so a flat index is instant and tiny. Chunk metadata
(text, source, heading) is stored alongside in JSON, aligned by row id.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

_INDEX_FILE = "index.faiss"
_META_FILE = "meta.json"


@dataclass(frozen=True, slots=True)
class Hit:
    """A search result chunk."""

    text: str
    source: str
    heading: str
    score: float


def _require_faiss():
    try:
        import faiss
        import numpy as np
    except ImportError as exc:
        from .embedder import DocsEmbedderUnavailable

        raise DocsEmbedderUnavailable(
            "docs search needs the 'docs' extra (faiss-cpu, numpy)"
        ) from exc
    return faiss, np


def save_index(index_dir: str, vectors: np.ndarray, meta: list[dict]) -> None:
    """Build a flat-IP index from `vectors` and persist it + metadata to `index_dir`."""
    faiss, _ = _require_faiss()
    path = Path(index_dir)
    path.mkdir(parents=True, exist_ok=True)
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    faiss.write_index(index, str(path / _INDEX_FILE))
    (path / _META_FILE).write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )


class DocsIndex:
    """Loaded FAISS index + chunk metadata, queried by an embedded vector."""

    def __init__(self, index, meta: list[dict]) -> None:
        self._index = index
        self._meta = meta

    @classmethod
    def load(cls, index_dir: str) -> DocsIndex | None:
        """Load a persisted index, or None if it hasn't been built yet."""
        faiss, _ = _require_faiss()
        path = Path(index_dir)
        idx_file, meta_file = path / _INDEX_FILE, path / _META_FILE
        if not (idx_file.exists() and meta_file.exists()):
            return None
        index = faiss.read_index(str(idx_file))
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        return cls(index, meta)

    @property
    def size(self) -> int:
        return len(self._meta)

    def search(self, query_vec: np.ndarray, top_k: int = 5) -> list[Hit]:
        """Return the top_k most similar chunks for a (dim,) normalized query vector."""
        _, np = _require_faiss()
        if self._index.ntotal == 0:
            return []
        q = np.asarray(query_vec, dtype=np.float32).reshape(1, -1)
        k = min(top_k, self._index.ntotal)
        scores, ids = self._index.search(q, k)
        hits: list[Hit] = []
        for score, i in zip(scores[0], ids[0], strict=False):
            if i < 0:
                continue
            m = self._meta[i]
            hits.append(
                Hit(text=m["text"], source=m["source"], heading=m.get("heading", ""),
                    score=float(score))
            )
        return hits

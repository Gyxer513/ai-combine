"""Tests for local docs semantic search: chunker, store, and the search_docs tool gate.

The embedder (ONNX/EmbeddingGemma) is never loaded here — it's mocked. FAISS-backed
store tests are skipped if the `docs` extra isn't installed.
"""

from __future__ import annotations

import pytest

import src.orchestrator.tools.docs as docs_tool
from src.docs_search.chunker import markdown_chunks
from src.orchestrator.config import settings
from src.orchestrator.tools.docs import run_search

# --- chunker ---


def test_markdown_chunks_tracks_heading_trail():
    md = "# Title\n\nintro text\n\n## Section A\n\nbody a\n\n### Sub\n\ndeep body"
    chunks = markdown_chunks(md, "doc.md", chunk_chars=1000, overlap=100)
    trails = {c.heading for c in chunks}
    assert "Title" in trails
    assert "Title > Section A" in trails
    assert "Title > Section A > Sub" in trails
    assert all(c.source == "doc.md" for c in chunks)


def test_markdown_chunks_windows_long_section():
    body = "para. " * 600  # ~3600 chars, one heading
    chunks = markdown_chunks(f"# H\n\n{body}", "d.md", chunk_chars=1000, overlap=100)
    assert len(chunks) >= 3
    assert all(len(c.text) <= 1000 for c in chunks)
    assert all(c.heading == "H" for c in chunks)


def test_markdown_chunks_empty():
    assert markdown_chunks("", "d.md", chunk_chars=500, overlap=50) == []


# --- store (needs faiss) ---


def test_store_roundtrip(tmp_path):
    pytest.importorskip("faiss")
    import numpy as np

    from src.docs_search.store import DocsIndex, save_index

    vecs = np.eye(3, dtype=np.float32)  # 3 orthonormal vectors
    meta = [
        {"text": "alpha", "source": "a.md", "heading": "A"},
        {"text": "beta", "source": "b.md", "heading": "B"},
        {"text": "gamma", "source": "c.md", "heading": ""},
    ]
    save_index(str(tmp_path), vecs, meta)

    index = DocsIndex.load(str(tmp_path))
    assert index is not None and index.size == 3
    hits = index.search(np.array([1.0, 0.0, 0.0], dtype=np.float32), top_k=2)
    assert hits[0].text == "alpha" and hits[0].source == "a.md"
    assert hits[0].score > hits[1].score


def test_store_load_missing(tmp_path):
    pytest.importorskip("faiss")
    from src.docs_search.store import DocsIndex

    assert DocsIndex.load(str(tmp_path)) is None  # nothing built yet


# --- tool gate (embedder/index mocked) ---


async def test_run_search_disabled(monkeypatch):
    monkeypatch.setattr(settings, "docs_search_enabled", False)
    out = await run_search("how does the sandbox work")
    assert "disabled" in out


async def test_run_search_index_not_built(monkeypatch):
    monkeypatch.setattr(settings, "docs_search_enabled", True)
    monkeypatch.setattr(docs_tool, "_index", lambda: None)
    out = await run_search("anything")
    assert "hasn't been built" in out


async def test_run_search_extra_missing(monkeypatch):
    monkeypatch.setattr(settings, "docs_search_enabled", True)

    def boom():
        raise RuntimeError("docs search needs the 'docs' extra")

    monkeypatch.setattr(docs_tool, "_index", boom)
    out = await run_search("anything")
    assert "unavailable" in out and "extra" in out


async def test_run_search_returns_hits(monkeypatch):
    monkeypatch.setattr(settings, "docs_search_enabled", True)

    class _Hit:
        text, source, heading, score = "sandbox info", "docs/architecture.md", "Sandbox", 0.9

    class _Index:
        def search(self, qv, top_k):
            return [_Hit()]

    class _Emb:
        def embed_one(self, q, *, kind):
            return [0.1, 0.2]

    monkeypatch.setattr(docs_tool, "_index", lambda: _Index())
    monkeypatch.setattr(docs_tool, "_embedder", lambda: _Emb())
    out = await run_search("how is the sandbox isolated")
    assert "sandbox info" in out
    assert "docs/architecture.md > Sandbox" in out
    assert "untrusted_content" in out  # wrapped

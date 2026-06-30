"""Embeddings via API (Alibaba text-embedding-v4 behind LiteLLM).

No local TEI/BGE-M3 — saving RAM. A single HTTP client to LiteLLM's `/v1/embeddings`,
using the same master key. Used by both the indexer and the on-the-fly search tool.
"""

from __future__ import annotations

import httpx

from ..config import settings


class EmbeddingClient:
    """Client for LiteLLM /v1/embeddings."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._http = http
        self._base_url = (base_url or settings.litellm_base_url).rstrip("/")
        self._model = model or settings.embed_model
        self._key = api_key or settings.litellm_master_key

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return vectors for a list of texts (in the original order)."""
        if not texts:
            return []
        resp = await self._http.post(
            f"{self._base_url}/embeddings",
            headers={"Authorization": f"Bearer {self._key}"},
            json={"model": self._model, "input": texts},
        )
        resp.raise_for_status()
        data = resp.json()
        items = sorted(data["data"], key=lambda d: d["index"])
        return [it["embedding"] for it in items]

    async def embed_one(self, text: str) -> list[float]:
        """Vector for a single text."""
        vectors = await self.embed([text])
        return vectors[0]

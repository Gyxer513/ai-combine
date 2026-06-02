"""Embeddings через API (Alibaba text-embedding-v4 за LiteLLM).

Без локального TEI/BGE-M3 — экономим RAM. Один HTTP-клиент к `/v1/embeddings`
LiteLLM, тем же мастер-ключом. Используется и индексатором, и инструментом
поиска на лету.
"""

from __future__ import annotations

import httpx

from ..config import settings


class EmbeddingClient:
    """Клиент к LiteLLM /v1/embeddings."""

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
        """Вернуть векторы для списка текстов (в исходном порядке)."""
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
        """Вектор одного текста."""
        vectors = await self.embed([text])
        return vectors[0]

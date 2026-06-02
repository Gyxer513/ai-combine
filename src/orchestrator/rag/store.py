"""Векторное хранилище поверх Qdrant.

Одна коллекция на namespace (`kb_<namespace>`), вектор `embed_dim`, метрика
cosine. Чанки документа адресуются по `doc_id`, чтобы при переиндексации удалять
старые версии перед вставкой новых.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient, models

from ..config import settings

# Стабильный namespace для генерации UUID точек из (doc_id, chunk_index).
_POINT_NS = uuid.UUID("a1b2c3d4-0000-4000-8000-000000000000")


@dataclass(slots=True)
class Hit:
    """Результат поиска: текст чанка, источник и скор."""

    text: str
    path: str
    source: str
    score: float


def point_id(doc_id: str, chunk_index: int) -> str:
    """Детерминированный id точки Qdrant для чанка документа."""
    return str(uuid.uuid5(_POINT_NS, f"{doc_id}::{chunk_index}"))


class VectorStore:
    """Обёртка над Qdrant: коллекции по namespace, upsert и поиск."""

    def __init__(self, *, url: str | None = None, dim: int | None = None) -> None:
        self._client = AsyncQdrantClient(url=url or settings.qdrant_url)
        self._dim = dim or settings.embed_dim

    @staticmethod
    def _collection(namespace: str) -> str:
        return f"kb_{namespace}"

    async def ensure_collection(self, namespace: str) -> None:
        name = self._collection(namespace)
        if not await self._client.collection_exists(name):
            await self._client.create_collection(
                name,
                vectors_config=models.VectorParams(
                    size=self._dim, distance=models.Distance.COSINE
                ),
            )

    async def delete_doc(self, namespace: str, doc_id: str) -> None:
        """Удалить все чанки документа (перед переиндексацией)."""
        name = self._collection(namespace)
        if not await self._client.collection_exists(name):
            return
        condition = models.FieldCondition(
            key="doc_id", match=models.MatchValue(value=doc_id)
        )
        await self._client.delete(
            name,
            points_selector=models.FilterSelector(filter=models.Filter(must=[condition])),
        )

    async def upsert(
        self, namespace: str, points: list[tuple[str, list[float], dict]]
    ) -> None:
        """Вставить точки: список (id, вектор, payload)."""
        if not points:
            return
        await self.ensure_collection(namespace)
        await self._client.upsert(
            self._collection(namespace),
            points=[
                models.PointStruct(id=pid, vector=vec, payload=payload)
                for pid, vec, payload in points
            ],
        )

    async def search(self, namespace: str, vector: list[float], *, top_k: int = 5) -> list[Hit]:
        name = self._collection(namespace)
        if not await self._client.collection_exists(name):
            return []
        res = await self._client.query_points(
            name, query=vector, limit=top_k, with_payload=True
        )
        hits: list[Hit] = []
        for p in res.points:
            payload = p.payload or {}
            hits.append(
                Hit(
                    text=payload.get("text", ""),
                    path=payload.get("path", ""),
                    source=payload.get("source", ""),
                    score=p.score,
                )
            )
        return hits

    async def close(self) -> None:
        await self._client.close()

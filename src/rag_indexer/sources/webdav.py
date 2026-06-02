"""Источник: файлы Nextcloud через WebDAV.

Папки и их namespace задаются в `rag_webdav_folders` (CSV "/путь:namespace").
Индексируются текстовые форматы (md/txt/markdown/html). webdav4 синхронный —
запускаем в треде через asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
import os

import structlog
from webdav4.client import Client

from src.orchestrator.config import settings

from ..base import RagDocument

log = structlog.get_logger()

SUPPORTED_EXT = {".md", ".markdown", ".txt", ".html"}


def _client() -> Client:
    base = settings.nextcloud_url.rstrip("/") + f"/remote.php/dav/files/{settings.nextcloud_user}/"
    return Client(base, auth=(settings.nextcloud_user, settings.nextcloud_app_password))


def _walk_folder(folder: str, namespace: str) -> list[RagDocument]:
    """Синхронно обойти папку и прочитать поддерживаемые файлы."""
    client = _client()
    docs: list[RagDocument] = []
    stack = [folder.strip("/")]
    while stack:
        path = stack.pop()
        try:
            entries = client.ls(path, detail=True)
        except Exception as exc:  # noqa: BLE001 — папки может не быть
            log.warning("webdav.ls_failed", path=path, error=str(exc))
            continue
        for item in entries:
            name = item.get("name", "").rstrip("/")
            if not name or name == path.rstrip("/"):
                continue  # сама папка в выдаче ls
            if item.get("type") == "directory":
                stack.append(name)
                continue
            if os.path.splitext(name)[1].lower() not in SUPPORTED_EXT:
                continue
            try:
                with client.open(name, mode="r", encoding="utf-8") as f:
                    text = f.read()
            except Exception as exc:  # noqa: BLE001
                log.warning("webdav.read_failed", path=name, error=str(exc))
                continue
            if not text.strip():
                continue
            docs.append(
                RagDocument(
                    namespace=namespace,
                    doc_id=f"webdav:{name}",
                    source="webdav",
                    path=name,
                    text=text,
                    modified=str(item.get("modified", "")),
                )
            )
    return docs


async def fetch_webdav(_http=None) -> list[RagDocument]:
    """Забрать документы из всех настроенных WebDAV-папок."""
    folders = settings.webdav_folders
    if not (settings.nextcloud_url and folders):
        log.info("webdav.skip", reason="no folders configured")
        return []

    results = await asyncio.gather(
        *(asyncio.to_thread(_walk_folder, path, ns) for path, ns in folders)
    )
    docs = [d for batch in results for d in batch]
    log.info("webdav.fetched", count=len(docs))
    return docs

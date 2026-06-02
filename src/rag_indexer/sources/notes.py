"""Источник: Nextcloud Notes (тот же API, что у заметок).

Категория заметки маппится в namespace через `rag_notes_category_map`
(несопоставленные → `rag_notes_default_ns`).
"""

from __future__ import annotations

import httpx
import structlog

from src.orchestrator.config import settings

from ..base import RagDocument

log = structlog.get_logger()

NOTES_API = "/index.php/apps/notes/api/v1/notes"


async def fetch_notes(http: httpx.AsyncClient) -> list[RagDocument]:
    """Забрать все заметки и превратить в документы."""
    if not (settings.nextcloud_url and settings.nextcloud_user):
        log.info("notes.skip", reason="nextcloud creds not set")
        return []

    url = settings.nextcloud_url.rstrip("/") + NOTES_API
    auth = (settings.nextcloud_user, settings.nextcloud_app_password)
    try:
        resp = await http.get(url, auth=auth, timeout=30)
        resp.raise_for_status()
        notes = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("notes.fetch_failed", error=str(exc))
        return []

    cat_map = settings.notes_category_map
    docs: list[RagDocument] = []
    for n in notes:
        content = (n.get("content") or "").strip()
        if not content:
            continue
        category = (n.get("category") or "").strip()
        namespace = cat_map.get(category, settings.rag_notes_default_ns)
        title = (n.get("title") or f"note-{n.get('id')}").strip()
        docs.append(
            RagDocument(
                namespace=namespace,
                doc_id=f"note:{n.get('id')}",
                source="notes",
                path=f"Notes/{category or 'Uncategorized'}/{title}",
                text=f"# {title}\n\n{content}",
                modified=str(n.get("modified", "")),
            )
        )
    log.info("notes.fetched", count=len(docs))
    return docs

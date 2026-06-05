"""Клиент Nextcloud Notes (REST) для летописца: список, поиск, создание, дозапись."""

from __future__ import annotations

from typing import Any

import httpx

_API = "/index.php/apps/notes/api/v1"


class NotesClient:
    """Тонкий async-клиент к Nextcloud Notes (basic auth, app password)."""

    def __init__(self, http: httpx.AsyncClient, base_url: str, user: str, password: str) -> None:
        self._http = http
        self._base = base_url.rstrip("/")
        self._auth = (user, password)

    async def list_notes(self) -> list[dict]:
        resp = await self._http.get(f"{self._base}{_API}/notes", auth=self._auth, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []

    async def find_by_title(self, title: str) -> dict | None:
        for note in await self.list_notes():
            if note.get("title") == title:
                return note
        return None

    async def create(self, title: str, content: str, category: str = "") -> dict:
        body: dict[str, Any] = {"title": title, "content": content, "category": category}
        resp = await self._http.post(
            f"{self._base}{_API}/notes", json=body, auth=self._auth, timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    async def set_content(self, note_id: int, content: str) -> None:
        resp = await self._http.put(
            f"{self._base}{_API}/notes/{note_id}",
            json={"content": content},
            auth=self._auth,
            timeout=30,
        )
        resp.raise_for_status()

    async def append_section(
        self, *, title: str, category: str, heading: str, body: str
    ) -> None:
        """Дописать раздел в заметку (создать, если нет). Новое — сверху, под H1."""
        note = await self.find_by_title(title)
        section = f"## {heading}\n\n{body}\n"
        if note is None:
            await self.create(title, f"# {title}\n\n{section}", category)
            return
        old = note.get("content") or f"# {title}\n"
        # Вставляем новую запись сразу после первой строки-заголовка (H1).
        lines = old.split("\n", 1)
        head = lines[0]
        rest = lines[1] if len(lines) > 1 else ""
        await self.set_content(note["id"], f"{head}\n\n{section}\n{rest}".rstrip() + "\n")

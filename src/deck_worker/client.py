"""Клиент Nextcloud Deck (REST API) для worker'а.

Deck отдаёт массивы; MCP-обёртка кладёт их в `{"result": [...]}`, сырой API — нет,
поэтому `_unwrap` поддерживает оба варианта. Аутентификация — basic auth
(NEXTCLOUD_USER + app password, те же, что у RAG).

Эндпоинты:
* boards/stacks — `/index.php/apps/deck/api/v1.0/...`
* перенос карточки — `.../cards/{id}/reorder` (order + целевой stackId)
* комментарий — OCS `/ocs/v2.php/apps/deck/api/v1.0/cards/{id}/comments`
"""

from __future__ import annotations

from typing import Any

import httpx

_API = "/index.php/apps/deck/api/v1.0"
_OCS = "/ocs/v2.php/apps/deck/api/v1.0"
_COMMENT_LIMIT = 1000  # лимит длины комментария Deck
_TITLE_LIMIT = 255  # лимит длины заголовка карточки Deck


def _unwrap(data: Any) -> Any:
    """Развернуть массив из сырого ответа или из {'result': [...]}."""
    if isinstance(data, dict) and "result" in data:
        return data["result"]
    return data


class DeckClient:
    """Тонкий async-клиент к Nextcloud Deck."""

    def __init__(self, http: httpx.AsyncClient, base_url: str, user: str, password: str) -> None:
        self._http = http
        self._base = base_url.rstrip("/")
        self._auth = (user, password)
        self._headers = {
            "OCS-APIRequest": "true",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _get(self, path: str) -> Any:
        resp = await self._http.get(
            f"{self._base}{path}", auth=self._auth, headers=self._headers, timeout=30
        )
        resp.raise_for_status()
        return _unwrap(resp.json())

    async def boards(self) -> list[dict]:
        return await self._get(f"{_API}/boards")

    async def find_board(self, title: str) -> dict | None:
        for board in await self.boards():
            if board.get("title") == title:
                return board
        return None

    async def stacks(self, board_id: int) -> list[dict]:
        """Стеки доски с вложенными карточками (cards может быть None)."""
        return await self._get(f"{_API}/boards/{board_id}/stacks")

    async def board_card_titles(self, board_id: int) -> set[str]:
        """Все заголовки карточек доски (для антидубля)."""
        titles: set[str] = set()
        for stack in await self.stacks(board_id):
            for card in stack.get("cards") or []:
                title = (card.get("title") or "").strip()
                if title:
                    titles.add(title)
        return titles

    async def create_card(
        self, board_id: int, stack_id: int, title: str, description: str = "", *, order: int = 0
    ) -> dict:
        """Создать карточку в стеке."""
        resp = await self._http.post(
            f"{self._base}{_API}/boards/{board_id}/stacks/{stack_id}/cards",
            json={
                "title": title[:_TITLE_LIMIT],
                "type": "plain",
                "order": order,
                "description": description,
            },
            auth=self._auth,
            headers=self._headers,
            timeout=30,
        )
        resp.raise_for_status()
        return _unwrap(resp.json())

    async def move_card(
        self, board_id: int, card_id: int, target_stack_id: int, *, order: int = 0
    ) -> None:
        """Перенести карточку в стек `target_stack_id` (claim/Done).

        ВАЖНО: Deck-`reorder` ожидает в URL ЦЕЛЕВОЙ стек, а не исходный — иначе
        возвращает 200, но карточку между стеками не переносит (проверено на живом API).
        """
        resp = await self._http.put(
            f"{self._base}{_API}/boards/{board_id}/stacks/{target_stack_id}/cards/{card_id}/reorder",
            json={"order": order, "stackId": target_stack_id},
            auth=self._auth,
            headers=self._headers,
            timeout=30,
        )
        resp.raise_for_status()

    async def add_comment(self, card_id: int, message: str) -> None:
        """Добавить комментарий к карточке (OCS API, с усечением по лимиту)."""
        text = message[:_COMMENT_LIMIT]
        if len(message) > _COMMENT_LIMIT:
            text = text[:-15] + "\n…(обрезано)"
        resp = await self._http.post(
            f"{self._base}{_OCS}/cards/{card_id}/comments?format=json",
            json={"message": text},
            auth=self._auth,
            headers=self._headers,
            timeout=30,
        )
        resp.raise_for_status()

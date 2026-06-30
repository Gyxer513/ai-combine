"""Nextcloud Deck client (REST API) for the worker.

Deck returns arrays; the MCP wrapper puts them in `{"result": [...]}`, the raw API
does not, so `_unwrap` handles both shapes. Authentication is basic auth
(NEXTCLOUD_USER + app password, the same as RAG).

Endpoints:
* boards/stacks — `/index.php/apps/deck/api/v1.0/...`
* move a card — `.../cards/{id}/reorder` (order + target stackId)
* comment — OCS `/ocs/v2.php/apps/deck/api/v1.0/cards/{id}/comments`
"""

from __future__ import annotations

from typing import Any

import httpx

_API = "/index.php/apps/deck/api/v1.0"
_OCS = "/ocs/v2.php/apps/deck/api/v1.0"
_COMMENT_LIMIT = 1000  # Deck comment length limit
_TITLE_LIMIT = 255  # Deck card title length limit


def _unwrap(data: Any) -> Any:
    """Unwrap an array from a raw response or from {'result': [...]}."""
    if isinstance(data, dict) and "result" in data:
        return data["result"]
    return data


class DeckClient:
    """Thin async client for Nextcloud Deck."""

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
        """Board stacks with nested cards (cards may be None)."""
        return await self._get(f"{_API}/boards/{board_id}/stacks")

    async def board_card_titles(self, board_id: int) -> set[str]:
        """All card titles on the board (for de-duplication)."""
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
        """Create a card in a stack."""
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

    async def assign_label(
        self, board_id: int, stack_id: int, card_id: int, label_id: int
    ) -> None:
        """Attach a label to a card (Deck assignLabel)."""
        resp = await self._http.put(
            f"{self._base}{_API}/boards/{board_id}/stacks/{stack_id}/cards/{card_id}/assignLabel",
            json={"labelId": label_id},
            auth=self._auth,
            headers=self._headers,
            timeout=30,
        )
        resp.raise_for_status()

    async def move_card(
        self, board_id: int, card_id: int, target_stack_id: int, *, order: int = 0
    ) -> None:
        """Move a card to stack `target_stack_id` (claim/Done).

        IMPORTANT: Deck `reorder` expects the TARGET stack in the URL, not the source
        one — otherwise it returns 200 but does not move the card between stacks
        (verified against the live API).
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
        """Add a comment to a card (OCS API, truncated to the limit)."""
        text = message[:_COMMENT_LIMIT]
        if len(message) > _COMMENT_LIMIT:
            text = text[:-13] + "\n…(truncated)"
        resp = await self._http.post(
            f"{self._base}{_OCS}/cards/{card_id}/comments?format=json",
            json={"message": text},
            auth=self._auth,
            headers=self._headers,
            timeout=30,
        )
        resp.raise_for_status()

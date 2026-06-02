"""HTTP-клиент бота к оркестратору (/chat)."""

from __future__ import annotations

import httpx


class OrchestratorClient:
    """Тонкая обёртка над /chat оркестратора."""

    def __init__(self, http: httpx.AsyncClient, base_url: str) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")

    async def chat(self, *, message: str, agent: str, conversation_id: str) -> str:
        """Отправить сообщение агенту, вернуть текст ответа."""
        resp = await self._http.post(
            f"{self._base_url}/chat",
            json={"message": message, "agent": agent, "conversation_id": conversation_id},
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()["reply"]

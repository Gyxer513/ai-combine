"""Веб-поиск для агентов.

Этап 2: лёгкий клиент к DuckDuckGo без сторонних зависимостей и без парсинга
HTML — используется JSON Instant Answer API. Этого достаточно как стартовый
инструмент Колобка; на проде источник легко заменить на self-hosted SearXNG,
не трогая интерфейс `WebSearchClient.search`.

HTTP-клиент инъектируется снаружи (общий `httpx.AsyncClient` оркестратора),
что делает инструмент тестируемым без реальной сети.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import structlog

log = structlog.get_logger()

DUCKDUCKGO_IA_URL = "https://api.duckduckgo.com/"


@dataclass(slots=True)
class SearchResult:
    """Одна находка поиска."""

    title: str
    url: str
    snippet: str

    def as_line(self) -> str:
        """Компактное текстовое представление для LLM."""
        head = self.title or self.url
        body = f"{head}\n{self.snippet}".strip()
        return f"{body}\n{self.url}".strip() if self.url else body


class WebSearchClient:
    """Поиск в вебе через DuckDuckGo Instant Answer API."""

    def __init__(self, http: httpx.AsyncClient, *, base_url: str = DUCKDUCKGO_IA_URL) -> None:
        self._http = http
        self._base_url = base_url

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        """Вернуть до `max_results` находок по запросу.

        При сетевой ошибке возвращает пустой список (инструмент не должен
        ронять весь запрос агента) и пишет предупреждение в лог.
        """
        params = {
            "q": query,
            "format": "json",
            "no_html": "1",
            "no_redirect": "1",
            "skip_disambig": "1",
        }
        try:
            resp = await self._http.get(self._base_url, params=params)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("web_search.failed", query=query, error=str(exc))
            return []

        return _parse_instant_answer(data, max_results=max_results)


def _parse_instant_answer(data: dict, *, max_results: int) -> list[SearchResult]:
    """Разобрать ответ Instant Answer API в плоский список находок."""
    results: list[SearchResult] = []

    abstract = (data.get("AbstractText") or "").strip()
    if abstract:
        results.append(
            SearchResult(
                title=(data.get("Heading") or "").strip(),
                url=(data.get("AbstractURL") or "").strip(),
                snippet=abstract,
            )
        )

    for topic in _iter_related_topics(data.get("RelatedTopics", [])):
        if len(results) >= max_results:
            break
        text = (topic.get("Text") or "").strip()
        url = (topic.get("FirstURL") or "").strip()
        if not text:
            continue
        title, _, rest = text.partition(" - ")
        results.append(SearchResult(title=title.strip(), url=url, snippet=rest.strip() or text))

    return results[:max_results]


def _iter_related_topics(topics: list):
    """Развернуть вложенные группы RelatedTopics (поля `Topics`) в плоскую ленту."""
    for item in topics:
        if not isinstance(item, dict):
            continue
        if "Topics" in item and isinstance(item["Topics"], list):
            yield from _iter_related_topics(item["Topics"])
        else:
            yield item

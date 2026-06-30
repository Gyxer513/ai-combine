"""Web search for the agents.

The primary source is self-hosted **SearXNG** (a metasearch engine, JSON API): it
gives decent results with titles/snippets and does not depend on an external SaaS.
If SearXNG is unavailable or returns nothing — fall back to the DuckDuckGo Instant
Answer API (JSON, no HTML parsing). If that is empty too — an empty list (the tool
must not crash the agent's request).

The HTTP client is injected from outside (the orchestrator's shared
`httpx.AsyncClient`) — the tool is tested without a real network.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import structlog

from ..config import settings

log = structlog.get_logger()

DUCKDUCKGO_IA_URL = "https://api.duckduckgo.com/"


@dataclass(slots=True)
class SearchResult:
    """A single search result."""

    title: str
    url: str
    snippet: str

    def as_line(self) -> str:
        """Compact text representation for the LLM."""
        head = self.title or self.url
        body = f"{head}\n{self.snippet}".strip()
        return f"{body}\n{self.url}".strip() if self.url else body


class WebSearchClient:
    """Web search: SearXNG with a DuckDuckGo fallback."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        searxng_url: str | None = None,
        ddg_url: str = DUCKDUCKGO_IA_URL,
    ) -> None:
        self._http = http
        self._searxng_url = (searxng_url or settings.searxng_url).rstrip("/")
        self._ddg_url = ddg_url

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        """Return up to `max_results` results: SearXNG first, then DuckDuckGo."""
        results = await self._search_searxng(query, max_results=max_results)
        if results:
            return results
        return await self._search_ddg(query, max_results=max_results)

    async def _search_searxng(self, query: str, *, max_results: int) -> list[SearchResult]:
        """Request to the SearXNG JSON API."""
        params = {"q": query, "format": "json", "language": "ru", "safesearch": "0"}
        try:
            resp = await self._http.get(f"{self._searxng_url}/search", params=params)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("web_search.searxng_failed", query=query, error=str(exc))
            return []

        out: list[SearchResult] = []
        for item in data.get("results", []):
            if len(out) >= max_results:
                break
            url = (item.get("url") or "").strip()
            title = (item.get("title") or "").strip()
            snippet = (item.get("content") or "").strip()
            if url:
                out.append(SearchResult(title=title, url=url, snippet=snippet))
        return out

    async def _search_ddg(self, query: str, *, max_results: int) -> list[SearchResult]:
        """Fallback: the DuckDuckGo Instant Answer API."""
        params = {
            "q": query,
            "format": "json",
            "no_html": "1",
            "no_redirect": "1",
            "skip_disambig": "1",
        }
        try:
            resp = await self._http.get(self._ddg_url, params=params)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("web_search.ddg_failed", query=query, error=str(exc))
            return []
        return _parse_instant_answer(data, max_results=max_results)


def _parse_instant_answer(data: dict, *, max_results: int) -> list[SearchResult]:
    """Parse a DuckDuckGo Instant Answer API response into a flat list of results."""
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
    """Flatten nested RelatedTopics groups (the `Topics` fields) into a flat feed."""
    for item in topics:
        if not isinstance(item, dict):
            continue
        if "Topics" in item and isinstance(item["Topics"], list):
            yield from _iter_related_topics(item["Topics"])
        else:
            yield item

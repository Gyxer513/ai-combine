"""Research-worker — periodic research of money-making ideas (assistant), token-frugal.

Does NOT use an agentic tool-loop (it burns tokens with a growing context). Instead a
deterministic pipeline runs once per pass:

    rotate the theme (by date) -> N SearXNG searches (0 tokens) -> ONE call to a cheap
    model (qwen-flash): "from these results give K new ideas, here is what already
    exists — don't repeat" -> cards on the "Ideas" Deck board.

One LLM call per pass + an output cap = predictably pennies.

Run: `python -m src.research_worker.main`
(loops when RESEARCH_INTERVAL_MIN>0, otherwise a single pass).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import date

import httpx
import structlog

from src.deck_worker.client import DeckClient
from src.orchestrator.config import settings
from src.orchestrator.tools.web_search import WebSearchClient

log = structlog.get_logger()

_SYSTEM = (
    "You are an assistant that helps find money-making opportunities for a "
    "self-builder developer (self-hosted, loves automation, AI, unconventional "
    "approaches). You propose CONCRETE, actionable ideas tailored to his profile, "
    "not generic advice. You respond with a STRICTLY valid JSON array, with no "
    "explanations or markdown. Write the ideas in Russian (the user's language)."
)


@dataclass(slots=True)
class Idea:
    title: str
    pitch: str
    effort: str
    potential: str
    source: str

    def as_description(self) -> str:
        parts = [self.pitch]
        if self.effort:
            parts.append(f"**Effort:** {self.effort}")
        if self.potential:
            parts.append(f"**Potential:** {self.potential}")
        if self.source:
            parts.append(f"**Source:** {self.source}")
        return "\n\n".join(p for p in parts if p)


def pick_theme(themes: list[str], ordinal: int) -> str:
    """Theme by rotation (deterministic from the day's ordinal number)."""
    return themes[ordinal % len(themes)]


def build_prompt(theme: str, snippets: str, existing: list[str], k: int) -> str:
    """User prompt: theme + search excerpts + de-duplication."""
    existing_block = "\n".join(f"- {t}" for t in sorted(existing)) or "(empty)"
    return (
        f"Theme for ideas: {theme}\n\n"
        f"Fresh search results:\n{snippets or '(search empty)'}\n\n"
        f"Already proposed earlier (do NOT repeat or rephrase these):\n{existing_block}\n\n"
        f"Give {k} NEW concrete money-making ideas on the theme. Format: a JSON array "
        'of objects with fields: "title" (brief, up to 80 chars), "pitch" (1-2 sentences), '
        '"effort" (low/medium/high), "potential" (estimated monthly income), '
        '"source" (url from the results or ""). JSON only. Write the ideas in Russian.'
    )


def parse_ideas(content: str) -> list[Idea]:
    """Extract the JSON array of ideas from the model's reply (tolerant of wrappers/junk)."""
    start, end = content.find("["), content.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        raw = json.loads(content[start : end + 1])
    except (ValueError, TypeError):
        return []
    ideas: list[Idea] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        ideas.append(
            Idea(
                title=title,
                pitch=str(item.get("pitch") or "").strip(),
                effort=str(item.get("effort") or "").strip(),
                potential=str(item.get("potential") or "").strip(),
                source=str(item.get("source") or "").strip(),
            )
        )
    return ideas


async def gather_snippets(web: WebSearchClient, theme: str, n_searches: int) -> str:
    """Run a few searches on the theme and collect compact excerpts."""
    queries = [
        f"{theme} money-making ideas 2026",
        f"{theme} how to monetize",
        f"{theme} side business",
    ][: max(1, n_searches)]
    lines: list[str] = []
    for q in queries:
        for r in await web.search(q, max_results=4):
            lines.append(f"- {r.title}: {r.snippet} ({r.url})")
    return "\n".join(lines[:20])


async def call_model(http: httpx.AsyncClient, system: str, user: str) -> str:
    """A single cheap-model call via LiteLLM (no tool-loop)."""
    resp = await http.post(
        f"{settings.litellm_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
        json={
            "model": settings.research_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": settings.research_max_tokens,
            "temperature": 0.7,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


async def run_once(http: httpx.AsyncClient, deck: DeckClient, *, ordinal: int) -> int:
    """A single research pass. Returns: how many new cards were created."""
    themes = settings.research_theme_list
    if not themes:
        log.warning("research.no_themes")
        return 0
    theme = pick_theme(themes, ordinal)

    board = await deck.find_board(settings.research_board)
    if board is None:
        log.warning("research.board_missing", board=settings.research_board)
        return 0
    stacks = await deck.stacks(board["id"])
    target = next((s for s in stacks if s.get("title") == settings.research_stack), None)
    if target is None:
        log.warning("research.stack_missing", stack=settings.research_stack)
        return 0

    existing = await deck.board_card_titles(board["id"])
    web = WebSearchClient(http)
    snippets = await gather_snippets(web, theme, settings.research_searches_per_run)

    content = await call_model(
        http,
        _SYSTEM,
        build_prompt(theme, snippets, sorted(existing), settings.research_ideas_per_run),
    )
    ideas = parse_ideas(content)

    seen_lower = {t.lower() for t in existing}
    created = 0
    for idea in ideas[: settings.research_ideas_per_run]:
        if idea.title.lower() in seen_lower:
            continue
        await deck.create_card(board["id"], target["id"], idea.title, idea.as_description())
        seen_lower.add(idea.title.lower())
        created += 1
    log.info("research.done", theme=theme, parsed=len(ideas), created=created)
    return created


async def run() -> None:
    if not (settings.nextcloud_url and settings.nextcloud_user and settings.nextcloud_app_password):
        raise SystemExit("NEXTCLOUD_URL/USER/APP_PASSWORD are not set for the research-worker")

    interval = settings.research_interval_min
    async with httpx.AsyncClient() as http:
        deck = DeckClient(
            http,
            settings.nextcloud_url,
            settings.nextcloud_user,
            settings.nextcloud_app_password,
        )
        log.info("research.start", board=settings.research_board, interval_min=interval)
        while True:
            try:
                await run_once(http, deck, ordinal=date.today().toordinal())
            except Exception as exc:  # noqa: BLE001 — the loop must not crash
                log.warning("research.cycle_failed", error=str(exc))
            if interval <= 0:
                return
            await asyncio.sleep(interval * 60)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

"""Research-worker — регулярный ресёрч идей заработка (assistant), без жора токенов.

НЕ использует agentic tool-loop (он жжёт токены растущим контекстом). Вместо этого
детерминированный конвейер на один прогон:

    ротация темы (по дате) -> N поисков SearXNG (0 токенов) -> ОДИН вызов дешёвой
    модели (qwen-flash): «из этих результатов дай K новых идей, вот что уже есть —
    не повторяй» -> карточки на Deck-доске «Идеи».

Один LLM-вызов на прогон + потолок вывода = предсказуемо копейки.

Запуск: `python -m src.research_worker.main`
(цикл при RESEARCH_INTERVAL_MIN>0, иначе один проход).
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
    "Ты — assistant, помощник по поиску возможностей заработка для разработчика-"
    "самостройщика (self-hosted, любит автоматизацию, AI, нестандартные подходы). "
    "Предлагаешь КОНКРЕТНЫЕ реализуемые идеи под его профиль, а не общие советы. "
    "Отвечаешь СТРОГО валидным JSON-массивом, без пояснений и markdown."
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
            parts.append(f"**Усилия:** {self.effort}")
        if self.potential:
            parts.append(f"**Потенциал:** {self.potential}")
        if self.source:
            parts.append(f"**Источник:** {self.source}")
        return "\n\n".join(p for p in parts if p)


def pick_theme(themes: list[str], ordinal: int) -> str:
    """Тема по ротации (детерминированно от порядкового номера дня)."""
    return themes[ordinal % len(themes)]


def build_prompt(theme: str, snippets: str, existing: list[str], k: int) -> str:
    """Пользовательский промпт: тема + выдержки поиска + антидубль."""
    existing_block = "\n".join(f"- {t}" for t in sorted(existing)) or "(пусто)"
    return (
        f"Тема для идей: {theme}\n\n"
        f"Свежие результаты поиска:\n{snippets or '(поиск пуст)'}\n\n"
        f"Уже предложено ранее (НЕ повторяй и не перефразируй это):\n{existing_block}\n\n"
        f"Дай {k} НОВЫЕ конкретные идеи заработка по теме. Формат — JSON-массив "
        'объектов с полями: "title" (кратко, до 80 симв.), "pitch" (1-2 предложения), '
        '"effort" (низкие/средние/высокие), "potential" (оценка дохода в месяц), '
        '"source" (url из результатов или ""). Только JSON.'
    )


def parse_ideas(content: str) -> list[Idea]:
    """Достать JSON-массив идей из ответа модели (терпимо к обёрткам/мусору)."""
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
    """Сделать несколько поисков по теме и собрать компактные выдержки."""
    queries = [
        f"{theme} идеи заработка 2026",
        f"{theme} как монетизировать",
        f"{theme} side business",
    ][: max(1, n_searches)]
    lines: list[str] = []
    for q in queries:
        for r in await web.search(q, max_results=4):
            lines.append(f"- {r.title}: {r.snippet} ({r.url})")
    return "\n".join(lines[:20])


async def call_model(http: httpx.AsyncClient, system: str, user: str) -> str:
    """Один вызов дешёвой модели через LiteLLM (без tool-loop)."""
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
    """Один прогон ресёрча. Возврат: сколько новых карточек создано."""
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
        raise SystemExit("Не заданы NEXTCLOUD_URL/USER/APP_PASSWORD для research-worker")

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
            except Exception as exc:  # noqa: BLE001 — цикл не должен падать
                log.warning("research.cycle_failed", error=str(exc))
            if interval <= 0:
                return
            await asyncio.sleep(interval * 60)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

"""GitHub-скил coder: чтение репозитория и внесение изменений через PR.

Перемычка для хоумлаба: рабочий GitLab за VPN недоступен надёжно, поэтому coder
пушит в GitHub (доступен отовсюду), а синхронизацию GitHub↔рабочий GitLab делает
человек вручную.

Работает через GitHub REST API с PAT (`Authorization: Bearer`). Токен — scoped на
конкретный репозиторий. Все изменения идут в feature-ветку + Pull Request; прямой
записи в основную ветку нет, человек ревьюит и мержит.

Инструменты coder: github_list_tree, github_read_file, github_commit_files, github_open_pr.
"""

from __future__ import annotations

import base64
from urllib.parse import quote

import httpx
import structlog
from pydantic_ai import Agent, RunContext

from ..config import settings
from .guard import wrap_untrusted

log = structlog.get_logger()


class GitHubClient:
    """Тонкий клиент к GitHub REST API для одного репозитория `owner/name`."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        api_url: str | None = None,
        token: str | None = None,
        repo: str | None = None,
        default_branch: str | None = None,
    ) -> None:
        self._http = http
        self._api = (api_url or settings.github_api_url).rstrip("/")
        self._token = token or settings.github_token
        self._repo = repo or settings.github_repo  # "owner/name"
        self.default_branch = default_branch or settings.github_default_branch

    @property
    def configured(self) -> bool:
        return bool(self._token and "/" in self._repo)

    def _url(self, path: str) -> str:
        return f"{self._api}/repos/{self._repo}{path}"

    def _headers(self, raw: bool = False) -> dict[str, str]:
        accept = "application/vnd.github.raw+json" if raw else "application/vnd.github+json"
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def list_tree(self, path: str = "", ref: str | None = None) -> list[dict]:
        resp = await self._http.get(
            self._url(f"/git/trees/{ref or self.default_branch}"),
            params={"recursive": "1"},
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        items = resp.json().get("tree", [])
        if path:
            items = [i for i in items if i.get("path", "").startswith(path)]
        return items

    async def read_file(self, path: str, ref: str | None = None) -> str:
        resp = await self._http.get(
            self._url(f"/contents/{quote(path)}"),
            params={"ref": ref or self.default_branch},
            headers=self._headers(raw=True),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.text

    async def _branch_sha(self, branch: str) -> str | None:
        resp = await self._http.get(
            self._url(f"/git/ref/heads/{branch}"), headers=self._headers(), timeout=30
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()["object"]["sha"]

    async def ensure_branch(self, branch: str, base: str) -> None:
        if await self._branch_sha(branch) is not None:
            return
        base_sha = await self._branch_sha(base)
        if base_sha is None:
            raise httpx.HTTPError(f"базовая ветка {base} не найдена")
        resp = await self._http.post(
            self._url("/git/refs"),
            json={"ref": f"refs/heads/{branch}", "sha": base_sha},
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()

    async def _file_sha(self, path: str, branch: str) -> str | None:
        resp = await self._http.get(
            self._url(f"/contents/{quote(path)}"),
            params={"ref": branch},
            headers=self._headers(),
            timeout=30,
        )
        return resp.json().get("sha") if resp.status_code == 200 else None

    async def commit_files(self, branch: str, message: str, files: list[dict]) -> int:
        """Записать набор файлов в feature-ветку (создаётся из default при необходимости).

        GitHub Contents API коммитит по одному файлу — здесь это цикл (по коммиту на
        файл). Для перемычки с ручной синхронизацией чистота истории неважна.
        Возвращает число записанных файлов.
        """
        await self.ensure_branch(branch, self.default_branch)
        for f in files:
            path = f["path"]
            body = {
                "message": f"{message} ({path})",
                "content": base64.b64encode(f["content"].encode("utf-8")).decode("ascii"),
                "branch": branch,
            }
            sha = await self._file_sha(path, branch)
            if sha:
                body["sha"] = sha
            resp = await self._http.put(
                self._url(f"/contents/{quote(path)}"),
                json=body,
                headers=self._headers(),
                timeout=60,
            )
            resp.raise_for_status()
        return len(files)

    async def open_pr(self, head: str, title: str, body: str = "") -> dict:
        resp = await self._http.post(
            self._url("/pulls"),
            json={"title": title, "head": head, "base": self.default_branch, "body": body},
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()


def register_github_tools(agent: Agent) -> None:
    """Навесить на агента GitHub-инструменты (no-op, если GitHub не сконфигурирован)."""

    def _client(ctx: RunContext) -> GitHubClient | None:
        return getattr(ctx.deps, "github", None)

    @agent.tool
    async def github_list_tree(ctx: RunContext, path: str = "", ref: str = "") -> str:
        """Список файлов репозитория (рекурсивно, можно отфильтровать по path).

        Args:
            path: Префикс пути (пусто = весь репозиторий).
            ref: Ветка/тег (пусто = основная ветка).
        """
        gh = _client(ctx)
        if gh is None or not gh.configured:
            return "GitHub не настроен (нет GITHUB_TOKEN/REPO)."
        items = await gh.list_tree(path, ref or None)
        return "\n".join(f"{i.get('type', '?')}\t{i.get('path', '')}" for i in items) or "(пусто)"

    @agent.tool
    async def github_read_file(ctx: RunContext, path: str, ref: str = "") -> str:
        """Прочитать файл из репозитория.

        Args:
            path: Путь к файлу.
            ref: Ветка/тег (пусто = основная ветка).
        """
        gh = _client(ctx)
        if gh is None or not gh.configured:
            return "GitHub не настроен."
        try:
            content = await gh.read_file(path, ref or None)
        except httpx.HTTPStatusError as exc:
            return f"[не удалось прочитать {path}: {exc.response.status_code}]"
        return wrap_untrusted(f"github:{path}", content)

    @agent.tool
    async def github_commit_files(
        ctx: RunContext, branch: str, message: str, files: list[dict]
    ) -> str:
        """Закоммитить набор файлов в feature-ветку (создаётся при необходимости).

        НЕ коммить в основную ветку — только feature-ветка, потом открой PR.

        Args:
            branch: Имя feature-ветки (например feature/mis-report).
            message: Сообщение коммита.
            files: Список {"path": "путь", "content": "содержимое"}.
        """
        gh = _client(ctx)
        if gh is None or not gh.configured:
            return "GitHub не настроен."
        if branch == gh.default_branch:
            return f"Нельзя коммитить в {gh.default_branch}. Используй feature-ветку + PR."
        try:
            n = await gh.commit_files(branch, message, files)
        except httpx.HTTPStatusError as exc:
            return f"[ошибка коммита: {exc.response.status_code} {exc.response.text[:200]}]"
        return f"Записано {n} файл(ов) в ветку {branch}."

    @agent.tool
    async def github_open_pr(
        ctx: RunContext, branch: str, title: str, description: str = ""
    ) -> str:
        """Открыть Pull Request из feature-ветки в основную (на ревью человеку).

        Args:
            branch: Feature-ветка с изменениями.
            title: Заголовок PR.
            description: Описание (что сделано).
        """
        gh = _client(ctx)
        if gh is None or not gh.configured:
            return "GitHub не настроен."
        try:
            pr = await gh.open_pr(branch, title, description)
        except httpx.HTTPStatusError as exc:
            return f"[ошибка PR: {exc.response.status_code} {exc.response.text[:200]}]"
        return f"PR открыт: {pr.get('html_url', pr.get('number', '?'))}"

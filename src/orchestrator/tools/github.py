"""coder GitHub skill: reading a repository and making changes via PR.

A homelab bridge: the work GitLab behind the VPN is not reliably reachable, so coder
pushes to GitHub (reachable from anywhere), and a human syncs GitHub↔work GitLab
manually.

Works through the GitHub REST API with a PAT (`Authorization: Bearer`). The token is
scoped to a specific repository. All changes go into a feature branch + Pull Request;
there is no direct write to the main branch, a human reviews and merges.

coder tools: github_list_tree, github_read_file, github_commit_files, github_open_pr.
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
    """Thin client to the GitHub REST API for a single `owner/name` repository."""

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
            raise httpx.HTTPError(f"base branch {base} not found")
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
        """Write a set of files to a feature branch (created from default if needed).

        The GitHub Contents API commits one file at a time — here that is a loop (one
        commit per file). For a bridge with manual syncing, a clean history does not
        matter. Returns the number of files written.
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
    """Attach GitHub tools to the agent (no-op if GitHub is not configured)."""

    def _client(ctx: RunContext) -> GitHubClient | None:
        return getattr(ctx.deps, "github", None)

    @agent.tool
    async def github_list_tree(ctx: RunContext, path: str = "", ref: str = "") -> str:
        """List repository files (recursively, optionally filtered by path).

        Args:
            path: Path prefix (empty = the whole repository).
            ref: Branch/tag (empty = the main branch).
        """
        gh = _client(ctx)
        if gh is None or not gh.configured:
            return "GitHub is not configured (no GITHUB_TOKEN/REPO)."
        items = await gh.list_tree(path, ref or None)
        return "\n".join(f"{i.get('type', '?')}\t{i.get('path', '')}" for i in items) or "(empty)"

    @agent.tool
    async def github_read_file(ctx: RunContext, path: str, ref: str = "") -> str:
        """Read a file from the repository.

        Args:
            path: Path to the file.
            ref: Branch/tag (empty = the main branch).
        """
        gh = _client(ctx)
        if gh is None or not gh.configured:
            return "GitHub is not configured."
        try:
            content = await gh.read_file(path, ref or None)
        except httpx.HTTPStatusError as exc:
            return f"[could not read {path}: {exc.response.status_code}]"
        return wrap_untrusted(f"github:{path}", content)

    @agent.tool
    async def github_commit_files(
        ctx: RunContext, branch: str, message: str, files: list[dict]
    ) -> str:
        """Commit a set of files to a feature branch (created if needed).

        Do NOT commit to the main branch — only a feature branch, then open a PR.

        Args:
            branch: Feature branch name (e.g. feature/mis-report).
            message: Commit message.
            files: List of {"path": "path", "content": "content"}.
        """
        gh = _client(ctx)
        if gh is None or not gh.configured:
            return "GitHub is not configured."
        if branch == gh.default_branch:
            return f"Cannot commit to {gh.default_branch}. Use a feature branch + PR."
        try:
            n = await gh.commit_files(branch, message, files)
        except httpx.HTTPStatusError as exc:
            return f"[commit error: {exc.response.status_code} {exc.response.text[:200]}]"
        return f"Wrote {n} file(s) to branch {branch}."

    @agent.tool
    async def github_open_pr(
        ctx: RunContext, branch: str, title: str, description: str = ""
    ) -> str:
        """Open a Pull Request from a feature branch into the main one (for human review).

        Args:
            branch: Feature branch with the changes.
            title: PR title.
            description: Description (what was done).
        """
        gh = _client(ctx)
        if gh is None or not gh.configured:
            return "GitHub is not configured."
        try:
            pr = await gh.open_pr(branch, title, description)
        except httpx.HTTPStatusError as exc:
            return f"[PR error: {exc.response.status_code} {exc.response.text[:200]}]"
        return f"PR opened: {pr.get('html_url', pr.get('number', '?'))}"

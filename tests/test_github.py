"""Тесты GitHub-клиента Левши (через httpx MockTransport)."""

from __future__ import annotations

import base64

import httpx

from src.orchestrator.tools.github import GitHubClient


def _client(handler, **kw) -> GitHubClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    kw.setdefault("api_url", "https://api.github.test")
    kw.setdefault("token", "tok")
    kw.setdefault("repo", "Gyxer513/mis-report")
    return GitHubClient(http, **kw)


def test_configured_flag():
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    assert GitHubClient(http, token="", repo="").configured is False
    assert GitHubClient(http, token="t", repo="owner/name").configured is True
    assert GitHubClient(http, token="t", repo="noslash").configured is False


async def test_read_file_raw_wrapped():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/repos/Gyxer513/mis-report/contents/" in str(request.url)
        assert request.headers["Authorization"] == "Bearer tok"
        assert "raw" in request.headers["Accept"]
        return httpx.Response(200, text="print('hi')")

    out = await _client(handler).read_file("app/main.py")
    assert out == "print('hi')"  # клиент отдаёт сырой текст; обёртка — на уровне tool


async def test_commit_files_creates_branch_and_writes():
    calls = {"branch_created": False, "puts": []}

    def handler(request: httpx.Request) -> httpx.Response:
        url, m = str(request.url), request.method
        if "/git/ref/heads/feature%2Fx" in url or "/git/ref/heads/feature/x" in url:
            return httpx.Response(404)  # ветки ещё нет
        if "/git/ref/heads/main" in url:
            return httpx.Response(200, json={"object": {"sha": "basesha"}})
        if url.endswith("/git/refs") and m == "POST":
            calls["branch_created"] = True
            assert b"refs/heads/feature/x" in request.read()
            return httpx.Response(201, json={})
        if "/contents/" in url and m == "GET":
            return httpx.Response(404)  # файла нет -> create
        if "/contents/" in url and m == "PUT":
            body = request.read().decode()
            calls["puts"].append(body)
            return httpx.Response(201, json={"commit": {"sha": "x"}})
        return httpx.Response(404)

    n = await _client(handler).commit_files(
        "feature/x", "msg", [{"path": "main.py", "content": "code"}]
    )
    assert n == 1
    assert calls["branch_created"] is True
    # контент уходит в base64
    assert base64.b64encode(b"code").decode() in calls["puts"][0]


async def test_open_pr_targets_default_branch():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/pulls")
        body = request.read().decode()
        assert '"base":"main"' in body
        assert '"head":"feature/x"' in body
        return httpx.Response(201, json={"html_url": "https://github.com/x/y/pull/1"})

    pr = await _client(handler).open_pr("feature/x", "T", "D")
    assert pr["html_url"].endswith("/pull/1")

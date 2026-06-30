"""Stage 6 tests (sandbox via the broker): broker client and tool registration."""

from __future__ import annotations

import httpx

from src.orchestrator.agents import coder, recon
from src.orchestrator.tools.shell import BrokerClient


def _client(handler) -> BrokerClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    return BrokerClient(http, base_url="http://broker.test")


async def test_broker_client_returns_output():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/run"
        body = request.read().decode()
        assert "secops" in body and "nmap" in body
        return httpx.Response(200, json={"output": "exit=0\nopen", "blocked": False})

    out = await _client(handler).run("secops", "nmap -V")
    assert "exit=0" in out


async def test_broker_client_surfaces_blocked():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"blocked": True, "reason": "binary «sh» not in allowlist"})

    out = await _client(handler).run("coder", "x | sh")
    assert "rejected by the broker" in out
    assert "sh" in out


async def test_broker_client_handles_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    out = await _client(handler).run("secops", "nmap -V")
    assert "unreachable" in out


def test_agents_have_shell_tools():
    assert "run_security_command" in recon.agent._function_toolset.tools
    assert "run_shell" in coder.agent._function_toolset.tools

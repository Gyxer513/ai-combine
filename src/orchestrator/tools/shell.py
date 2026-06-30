"""Command execution tools: client to the sandbox broker.

The orchestrator does NOT spawn containers itself and has no access to docker.sock —
it sends the command to the `sandbox-broker` over HTTP. The broker (the only one
with docker.sock) applies hardening and authoritatively validates the allowlist by
profile.

This module holds the client (`BrokerClient`) and the tool registration on the
agent. The local `CommandGuard` is kept as a fast reject before the network call
(UX); the real security boundary is on the broker side.
"""

from __future__ import annotations

import httpx
import structlog
from pydantic_ai import Agent, RunContext

from ..config import settings
from .guard import CommandGuard, wrap_untrusted

log = structlog.get_logger()


class BrokerClient:
    """HTTP client to the sandbox broker."""

    def __init__(self, http: httpx.AsyncClient, *, base_url: str | None = None) -> None:
        self._http = http
        self._base_url = (base_url or settings.broker_url).rstrip("/")

    async def run(self, profile: str, command: str) -> str:
        """Send the command to the broker, return the output (or an error message)."""
        try:
            resp = await self._http.post(
                f"{self._base_url}/run",
                json={"profile": profile, "command": command},
                timeout=settings.sandbox_timeout_sec + 30,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            log.warning("broker.unreachable", profile=profile, error=str(exc))
            return f"[sandbox-broker unreachable: {exc}]"
        if data.get("blocked"):
            return f"[command rejected by the broker: {data.get('reason', '')}]"
        return data.get("output", "")


def register_shell_tool(
    agent: Agent,
    *,
    profile: str,
    allowed: frozenset[str],
    name: str,
    what: str,
    network_note: str,
) -> None:
    """Attach a sandbox tool that runs through the broker.

    `profile` — broker section ("secops"/"coder"): defines the network and allowlist
    on the broker side. `allowed` — the same allowlist for the local fast reject.
    """
    guard = CommandGuard(allowed)

    async def shell_tool(ctx: RunContext, command: str) -> str:
        ok, reason = guard.check(command)
        if not ok:
            log.warning("sandbox.blocked_local", tool=name, reason=reason, command=command)
            return (
                f"[command rejected by the security policy: {reason}]\n"
                f"Only these are allowed: {', '.join(sorted(allowed))}. "
                "Rephrase it as a single allowed binary without substitutions."
            )
        if ctx.deps.broker is None:
            return "[sandbox unavailable: broker is not configured]"
        log.info("sandbox.run", tool=name, profile=profile)
        output = await ctx.deps.broker.run(profile, command)
        # Command output is untrusted (it may contain an injection from the target's
        # response).
        return wrap_untrusted(f"{name}_output", output)

    shell_tool.__name__ = name
    shell_tool.__doc__ = (
        f"{what} in an isolated sandbox ({network_note}). "
        "Takes a single shell command, returns the exit code and output.\n"
        f"Only these binaries are allowed: {', '.join(sorted(allowed))}. "
        "No substitutions ($(), ``), no chains to a disallowed binary.\n\n"
        "Args:\n    command: Command for bash -lc."
    )
    agent.tool(shell_tool)

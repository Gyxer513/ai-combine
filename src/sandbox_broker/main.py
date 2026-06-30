"""Sandbox-broker — isolated spawning of hardened containers.

This is the ONLY service that has `docker.sock` mounted in compose. It exposes a
minimal API:

    POST /run {profile, command} -> {output, blocked, reason}

The client (orchestrator) only specifies the profile and command. Everything else —
image, cap_drop, read-only rootfs, limits, network, user — is hardcoded here and is
NOT controlled from outside. The binary allowlist is checked right here
(authoritatively): even if the orchestrator is compromised by injection, it cannot
run an arbitrary docker container or bypass the allowlist.

Profiles:
    secops — network ON (scanning your infra), allowlist SECOPS_ALLOWED (no interpreters)
    coder  — network OFF (running code),       allowlist CODER_ALLOWED
"""

from __future__ import annotations

import asyncio

import structlog
from fastapi import FastAPI
from pydantic import BaseModel

# Reuse the shared guard/allowlist (sibling import, like telegram_bot/rag_indexer).
from src.orchestrator.config import settings
from src.orchestrator.tools.guard import CODER_ALLOWED, SECOPS_ALLOWED, CommandGuard

log = structlog.get_logger()

# Profile -> (network, allowlist). Server-side, the client has no say.
_PROFILES = {
    "secops": (True, SECOPS_ALLOWED),
    "coder": (False, CODER_ALLOWED),
}


class SandboxRunner:
    """Run a command in a single-use hardened container (docker SDK)."""

    def __init__(self, *, network: bool) -> None:
        self._network = network

    async def run(self, command: str) -> str:
        return await asyncio.to_thread(self._run_sync, command)

    def _run_sync(self, command: str) -> str:
        try:
            from docker.errors import DockerException, ImageNotFound

            import docker
        except ImportError:
            return "[sandbox unavailable: the docker package is not installed]"

        try:
            client = docker.from_env()
        except DockerException as exc:
            return f"[sandbox unavailable: no access to docker — {exc}]"

        kwargs = {
            "image": settings.sandbox_image,
            "command": ["bash", "-lc", command],
            "detach": True,
            "mem_limit": settings.sandbox_mem,
            "nano_cpus": int(settings.sandbox_cpus * 1_000_000_000),
            "pids_limit": settings.sandbox_pids,
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "read_only": True,
            "tmpfs": {"/tmp": "rw,size=128m,exec"},
            "working_dir": "/tmp",
            "user": "10001",
            "environment": {"HOME": "/tmp"},
        }
        if self._network:
            kwargs["network_mode"] = "bridge"
        else:
            kwargs["network_disabled"] = True

        try:
            container = client.containers.run(**kwargs)
        except ImageNotFound:
            return f"[sandbox image not found: {settings.sandbox_image}]"
        except DockerException as exc:
            return f"[sandbox startup error: {exc}]"

        try:
            result = container.wait(timeout=settings.sandbox_timeout_sec)
            logs = container.logs(stdout=True, stderr=True).decode("utf-8", "replace")
            code = result.get("StatusCode", "?")
        except Exception as exc:  # noqa: BLE001 — docker SDK timeout, etc.
            try:
                container.kill()
            except Exception:  # noqa: BLE001
                pass
            return f"[sandbox aborted (timeout {settings.sandbox_timeout_sec}s or error): {exc}]"
        finally:
            try:
                container.remove(force=True)
            except Exception:  # noqa: BLE001
                pass

        out = logs[: settings.sandbox_output_limit]
        if len(logs) > settings.sandbox_output_limit:
            out += "\n...[output truncated]"
        return f"exit={code}\n{out}".strip()


class RunRequest(BaseModel):
    profile: str
    command: str


class RunResponse(BaseModel):
    output: str = ""
    blocked: bool = False
    reason: str = ""


app = FastAPI(title="AI Combine Sandbox Broker", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/run", response_model=RunResponse)
async def run(req: RunRequest) -> RunResponse:
    """Run a command by profile. The allowlist is checked here authoritatively."""
    profile = _PROFILES.get(req.profile)
    if profile is None:
        log.warning("broker.unknown_profile", profile=req.profile)
        return RunResponse(blocked=True, reason=f"unknown profile «{req.profile}»")

    network, allowed = profile
    ok, reason = CommandGuard(allowed).check(req.command)
    if not ok:
        log.warning("broker.blocked", profile=req.profile, reason=reason, command=req.command)
        return RunResponse(blocked=True, reason=reason)

    log.info("broker.run", profile=req.profile, network=network)
    output = await SandboxRunner(network=network).run(req.command)
    return RunResponse(output=output)

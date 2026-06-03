"""Sandbox-broker — изолированное порождение hardened-контейнеров.

Это ЕДИНСТВЕННЫЙ сервис, которому в compose проброшен `docker.sock`. Он
экспонирует минимальный API:

    POST /run {profile, command} -> {output, blocked, reason}

Клиент (оркестратор) задаёт только профиль и команду. Всё остальное —
образ, cap_drop, read-only rootfs, лимиты, сеть, пользователь — захардкожено
здесь и НЕ управляется снаружи. Allowlist бинарей проверяется тут же
(авторитетно): даже если оркестратор скомпрометирован инъекцией, он не сможет
ни запустить произвольный docker, ни обойти allowlist.

Профили:
    secops — сеть ВКЛ (скан своей инфры), allowlist SECOPS_ALLOWED (без интерпретаторов)
    coder  — сеть ВЫКЛ (прогон кода),     allowlist CODER_ALLOWED
"""

from __future__ import annotations

import asyncio

import structlog
from fastapi import FastAPI
from pydantic import BaseModel

# Переиспользуем единый guard/allowlist (sibling-импорт, как telegram_bot/rag_indexer).
from src.orchestrator.config import settings
from src.orchestrator.tools.guard import CODER_ALLOWED, SECOPS_ALLOWED, CommandGuard

log = structlog.get_logger()

# Профиль -> (сеть, allowlist). Server-side, клиент не влияет.
_PROFILES = {
    "secops": (True, SECOPS_ALLOWED),
    "coder": (False, CODER_ALLOWED),
}


class SandboxRunner:
    """Запуск команды в одноразовом hardened-контейнере (docker SDK)."""

    def __init__(self, *, network: bool) -> None:
        self._network = network

    async def run(self, command: str) -> str:
        return await asyncio.to_thread(self._run_sync, command)

    def _run_sync(self, command: str) -> str:
        try:
            from docker.errors import DockerException, ImageNotFound

            import docker
        except ImportError:
            return "[sandbox недоступен: пакет docker не установлен]"

        try:
            client = docker.from_env()
        except DockerException as exc:
            return f"[sandbox недоступен: нет доступа к docker — {exc}]"

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
            return f"[sandbox образ не найден: {settings.sandbox_image}]"
        except DockerException as exc:
            return f"[sandbox ошибка запуска: {exc}]"

        try:
            result = container.wait(timeout=settings.sandbox_timeout_sec)
            logs = container.logs(stdout=True, stderr=True).decode("utf-8", "replace")
            code = result.get("StatusCode", "?")
        except Exception as exc:  # noqa: BLE001 — таймаут docker SDK и пр.
            try:
                container.kill()
            except Exception:  # noqa: BLE001
                pass
            return f"[sandbox прерван (таймаут {settings.sandbox_timeout_sec}s или ошибка): {exc}]"
        finally:
            try:
                container.remove(force=True)
            except Exception:  # noqa: BLE001
                pass

        out = logs[: settings.sandbox_output_limit]
        if len(logs) > settings.sandbox_output_limit:
            out += "\n...[вывод обрезан]"
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
    """Выполнить команду по профилю. Allowlist проверяется здесь авторитетно."""
    profile = _PROFILES.get(req.profile)
    if profile is None:
        log.warning("broker.unknown_profile", profile=req.profile)
        return RunResponse(blocked=True, reason=f"неизвестный профиль «{req.profile}»")

    network, allowed = profile
    ok, reason = CommandGuard(allowed).check(req.command)
    if not ok:
        log.warning("broker.blocked", profile=req.profile, reason=reason, command=req.command)
        return RunResponse(blocked=True, reason=reason)

    log.info("broker.run", profile=req.profile, network=network)
    output = await SandboxRunner(network=network).run(req.command)
    return RunResponse(output=output)

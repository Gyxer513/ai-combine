"""Изолированное исполнение команд в Docker-sandbox.

Запускает команду в эфемерном контейнере из образа `sandbox_image` с жёстким
hardening'ом: cap-drop ALL, no-new-privileges, read-only rootfs + tmpfs /tmp,
лимиты mem/cpu/pids, non-root user, таймаут. Сеть — по политике агента
(Кощей: включена для скана своей инфры; Левша: выключена для прогона кода).

ВНИМАНИЕ: оркестратору нужен доступ к docker.sock, чтобы порождать sandbox'ы.
Это привилегия — поэтому сами sandbox'ы максимально зажаты, эфемерны (--rm) и не
получают ни docker.sock, ни capabilities.
"""

from __future__ import annotations

import asyncio

import structlog
from pydantic_ai import Agent, RunContext

from ..config import settings
from .guard import CommandGuard, wrap_untrusted

log = structlog.get_logger()


class SandboxRunner:
    """Запуск команд в одноразовом hardened-контейнере."""

    def __init__(self, *, network: bool) -> None:
        self._network = network

    async def run(self, command: str) -> str:
        """Выполнить команду, вернуть exit-код и вывод (stdout+stderr)."""
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


def register_shell_tool(
    agent: Agent,
    *,
    network: bool,
    name: str,
    what: str,
    allowed: frozenset[str],
) -> None:
    """Навесить sandbox-инструмент с заданным именем, сетевой политикой и allowlist.

    `allowed` — множество разрешённых бинарей (см. guard.SECOPS_ALLOWED /
    CODER_ALLOWED). Команда проверяется ДО запуска: неразрешённый бинарь,
    подстановка или цепочка на чужой бинарь отклоняются, не доходя до sandbox.
    """
    runner = SandboxRunner(network=network)
    guard = CommandGuard(allowed)
    net_note = "есть сеть" if network else "БЕЗ сети"

    async def shell_tool(ctx: RunContext, command: str) -> str:
        ok, reason = guard.check(command)
        if not ok:
            log.warning("sandbox.blocked", tool=name, reason=reason, command=command)
            return (
                f"[команда отклонена политикой безопасности: {reason}]\n"
                f"Разрешены только: {', '.join(sorted(allowed))}. "
                "Переформулируй под один разрешённый бинарь без подстановок."
            )
        log.info("sandbox.run", tool=name, network=network)
        output = await runner.run(command)
        # Вывод команды — недоверенный (может содержать инъекцию из ответа цели).
        return wrap_untrusted(f"{name}_output", output)

    shell_tool.__name__ = name
    shell_tool.__doc__ = (
        f"{what} в изолированном sandbox ({net_note}). "
        "Принимает одну shell-команду, возвращает exit-код и вывод.\n"
        f"Разрешены только бинари: {', '.join(sorted(allowed))}. "
        "Без подстановок ($(), ``), без цепочек на неразрешённый бинарь.\n\n"
        "Args:\n    command: Команда для bash -lc."
    )
    agent.tool(shell_tool)

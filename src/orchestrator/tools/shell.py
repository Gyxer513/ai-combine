"""Инструменты исполнения команд: клиент к sandbox-broker.

Оркестратор САМ не порождает контейнеры и не имеет доступа к docker.sock —
он отправляет команду в `sandbox-broker` по HTTP. Брокер (единственный с
docker.sock) применяет hardening и авторитетно проверяет allowlist по профилю.

Здесь — клиент (`BrokerClient`) и регистрация инструмента на агенте. Локальный
`CommandGuard` оставлен как быстрый отказ до сетевого вызова (UX); настоящая
граница безопасности — на стороне брокера.
"""

from __future__ import annotations

import httpx
import structlog
from pydantic_ai import Agent, RunContext

from ..config import settings
from .guard import CommandGuard, wrap_untrusted

log = structlog.get_logger()


class BrokerClient:
    """HTTP-клиент к sandbox-broker."""

    def __init__(self, http: httpx.AsyncClient, *, base_url: str | None = None) -> None:
        self._http = http
        self._base_url = (base_url or settings.broker_url).rstrip("/")

    async def run(self, profile: str, command: str) -> str:
        """Отправить команду брокеру, вернуть вывод (или сообщение об ошибке)."""
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
            return f"[sandbox-broker недоступен: {exc}]"
        if data.get("blocked"):
            return f"[команда отклонена брокером: {data.get('reason', '')}]"
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
    """Навесить sandbox-инструмент, исполняющийся через брокер.

    `profile` — секция брокера ("secops"/"coder"): задаёт сеть и allowlist на
    стороне брокера. `allowed` — тот же allowlist для локального быстрого отказа.
    """
    guard = CommandGuard(allowed)

    async def shell_tool(ctx: RunContext, command: str) -> str:
        ok, reason = guard.check(command)
        if not ok:
            log.warning("sandbox.blocked_local", tool=name, reason=reason, command=command)
            return (
                f"[команда отклонена политикой безопасности: {reason}]\n"
                f"Разрешены только: {', '.join(sorted(allowed))}. "
                "Переформулируй под один разрешённый бинарь без подстановок."
            )
        if ctx.deps.broker is None:
            return "[sandbox недоступен: broker не сконфигурирован]"
        log.info("sandbox.run", tool=name, profile=profile)
        output = await ctx.deps.broker.run(profile, command)
        # Вывод команды — недоверенный (может содержать инъекцию из ответа цели).
        return wrap_untrusted(f"{name}_output", output)

    shell_tool.__name__ = name
    shell_tool.__doc__ = (
        f"{what} в изолированном sandbox ({network_note}). "
        "Принимает одну shell-команду, возвращает exit-код и вывод.\n"
        f"Разрешены только бинари: {', '.join(sorted(allowed))}. "
        "Без подстановок ($(), ``), без цепочек на неразрешённый бинарь.\n\n"
        "Args:\n    command: Команда для bash -lc."
    )
    agent.tool(shell_tool)

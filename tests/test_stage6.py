"""Тесты Этапа 6 (sandbox): hardened-исполнитель и регистрация инструментов."""

from __future__ import annotations

import docker
from src.orchestrator.agents import koschei, levsha
from src.orchestrator.tools.shell import SandboxRunner


class _FakeContainer:
    def __init__(self, code: int = 0, logs: bytes = b"ok\n") -> None:
        self._code = code
        self._logs = logs

    def wait(self, timeout=None):
        return {"StatusCode": self._code}

    def logs(self, **_kw):
        return self._logs

    def remove(self, force=False):
        pass

    def kill(self):
        pass


class _FakeContainers:
    def __init__(self) -> None:
        self.kwargs: dict | None = None

    def run(self, **kwargs):
        self.kwargs = kwargs
        return _FakeContainer()


class _FakeClient:
    def __init__(self) -> None:
        self.containers = _FakeContainers()


def _patch_docker(monkeypatch) -> _FakeClient:
    fake = _FakeClient()
    monkeypatch.setattr(docker, "from_env", lambda: fake)
    return fake


async def test_sandbox_runs_and_formats(monkeypatch):
    fake = _patch_docker(monkeypatch)
    out = await SandboxRunner(network=False).run("echo ok")
    assert "exit=0" in out
    assert "ok" in out
    # hardening применён
    kw = fake.containers.kwargs
    assert kw["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in kw["security_opt"]
    assert kw["read_only"] is True
    assert kw["user"] == "10001"


async def test_sandbox_network_off_by_default(monkeypatch):
    fake = _patch_docker(monkeypatch)
    await SandboxRunner(network=False).run("id")
    assert fake.containers.kwargs["network_disabled"] is True
    assert "network_mode" not in fake.containers.kwargs


async def test_sandbox_network_on_for_secops(monkeypatch):
    fake = _patch_docker(monkeypatch)
    await SandboxRunner(network=True).run("nmap -V")
    assert fake.containers.kwargs.get("network_mode") == "bridge"
    assert "network_disabled" not in fake.containers.kwargs


async def test_sandbox_output_truncated(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(docker, "from_env", lambda: fake)
    big = b"x" * 20000
    fake.containers.run = lambda **kw: _FakeContainer(logs=big)
    out = await SandboxRunner(network=False).run("yes")
    assert "[вывод обрезан]" in out


async def test_sandbox_docker_unavailable(monkeypatch):
    def boom():
        raise docker.errors.DockerException("no socket")

    monkeypatch.setattr(docker, "from_env", boom)
    out = await SandboxRunner(network=False).run("echo hi")
    assert "недоступен" in out


def test_agents_have_shell_tools():
    assert "run_security_command" in koschei.agent._function_toolset.tools
    assert "run_shell" in levsha.agent._function_toolset.tools

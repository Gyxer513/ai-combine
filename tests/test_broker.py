"""Sandbox-broker tests: the hardened runner and authoritative allowlist check."""

from __future__ import annotations

from fastapi.testclient import TestClient

import docker
from src.sandbox_broker.main import SandboxRunner, app


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
        self.called = False

    def run(self, **kwargs):
        self.called = True
        self.kwargs = kwargs
        return _FakeContainer()


class _FakeClient:
    def __init__(self) -> None:
        self.containers = _FakeContainers()


def _patch_docker(monkeypatch) -> _FakeClient:
    fake = _FakeClient()
    monkeypatch.setattr(docker, "from_env", lambda: fake)
    return fake


# --- hardened runner (moved from test_stage6) ---


async def test_sandbox_runs_and_hardening_applied(monkeypatch):
    fake = _patch_docker(monkeypatch)
    out = await SandboxRunner(network=False).run("echo ok")
    assert "exit=0" in out and "ok" in out
    kw = fake.containers.kwargs
    assert kw["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in kw["security_opt"]
    assert kw["read_only"] is True
    assert kw["user"] == "10001"


async def test_sandbox_network_policy(monkeypatch):
    fake = _patch_docker(monkeypatch)
    await SandboxRunner(network=False).run("id")
    assert fake.containers.kwargs["network_disabled"] is True
    fake2 = _patch_docker(monkeypatch)
    await SandboxRunner(network=True).run("nmap -V")
    assert fake2.containers.kwargs.get("network_mode") == "bridge"


async def test_sandbox_docker_unavailable(monkeypatch):
    def boom():
        raise docker.errors.DockerException("no socket")

    monkeypatch.setattr(docker, "from_env", boom)
    out = await SandboxRunner(network=False).run("echo hi")
    assert "unavailable" in out


# --- /run: authoritative allowlist check ---


def test_run_allows_secops_command(monkeypatch):
    fake = _patch_docker(monkeypatch)
    client = TestClient(app)
    resp = client.post("/run", json={"profile": "secops", "command": "nmap -V"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["blocked"] is False
    assert "exit=0" in data["output"]
    assert fake.containers.called is True


def test_run_blocks_interpreter_before_docker(monkeypatch):
    # docker.from_env would fail if called — but the guard must cut it off earlier
    def boom():
        raise AssertionError("docker must not be called for a blocked command")

    monkeypatch.setattr(docker, "from_env", boom)
    client = TestClient(app)
    resp = client.post("/run", json={"profile": "secops", "command": "python3 -c 'x'"})
    data = resp.json()
    assert data["blocked"] is True
    assert "allowlist" in data["reason"]


def test_run_unknown_profile():
    client = TestClient(app)
    resp = client.post("/run", json={"profile": "root", "command": "nmap -V"})
    data = resp.json()
    assert data["blocked"] is True
    assert "profile" in data["reason"]

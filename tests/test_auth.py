"""Тесты Bearer-аутентификации оркестратора (require_token)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.orchestrator.api.routes import require_token
from src.orchestrator.config import settings


async def test_require_token_disabled_when_empty(monkeypatch):
    # пустой токен -> enforcement выключен, любой запрос проходит
    monkeypatch.setattr(settings, "orchestrator_api_token", "")
    await require_token(authorization=None)  # не должно бросить


async def test_require_token_accepts_correct_bearer(monkeypatch):
    monkeypatch.setattr(settings, "orchestrator_api_token", "secret123")
    await require_token(authorization="Bearer secret123")  # ок


@pytest.mark.parametrize(
    "header",
    [None, "secret123", "Bearer wrong", "Basic secret123", "bearer secret123"],
)
async def test_require_token_rejects_bad_or_missing(monkeypatch, header):
    monkeypatch.setattr(settings, "orchestrator_api_token", "secret123")
    with pytest.raises(HTTPException) as exc:
        await require_token(authorization=header)
    assert exc.value.status_code == 401

"""Дымовые тесты каркаса оркестратора (Этап 1)."""

from fastapi.testclient import TestClient

from src.orchestrator.config import Settings
from src.orchestrator.main import app


def test_health_ok():
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


def test_allowed_user_ids_parsing():
    s = Settings(telegram_allowed_users="123, 456 ,789")
    assert s.allowed_user_ids == {123, 456, 789}


def test_allowed_user_ids_empty():
    s = Settings(telegram_allowed_users="")
    assert s.allowed_user_ids == set()

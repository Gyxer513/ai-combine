"""Общая настройка тестов.

Агенты на импорте собирают модель через LiteLLM-провайдер, которому нужен
непустой api_key. Чтобы тесты не зависели от реального `.env` разработчика,
подставляем фиктивные значения в окружение ДО импорта `src.orchestrator.config`
(переменные окружения имеют приоритет над .env в pydantic-settings).
"""

from __future__ import annotations

import os

# setdefault: если разработчик/CI задал реальные значения — не перетираем.
os.environ.setdefault("LITELLM_MASTER_KEY", "test-master-key")
os.environ.setdefault("LITELLM_BASE_URL", "http://litellm.test/v1")
# Тесты не должны писать SQLite-файл на диск — общая БД в памяти.
os.environ.setdefault("DB_PATH", ":memory:")

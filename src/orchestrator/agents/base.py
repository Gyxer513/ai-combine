"""Базовый агент с общей логикой (Pydantic AI).

Реализация на Этапе 2: общий клиент к LiteLLM, регистрация tools,
константа DATA_SENSITIVITY и выбор fallback-группы модели.
"""

from __future__ import annotations

from enum import StrEnum


class DataSensitivity(StrEnum):
    """Категория данных агента -> допустимость cloaked-моделей (см. план)."""

    PUBLIC = "public"  # любые free-модели
    INTERNAL = "internal"  # только open weights / платные
    SECRET = "secret"  # только платные / enterprise (Кощей)

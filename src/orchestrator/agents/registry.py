"""Реестр агентов: единая точка, откуда API берёт агента по имени.

Все трое (Колобок/Кощей/Левша) зарегистрированы и переключаются как отдельные
«модели» в OpenWebUI. Специфичные инструменты (RAG для Кощея, Gitea/sandbox для
Левши) дозаполняются на Этапах 3/6 — каркас и роутинг уже на месте.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent

from . import ded, kolobok, koschei, levsha
from .base import AgentDeps, DataSensitivity


@dataclass(frozen=True, slots=True)
class AgentCard:
    """Метаданные агента для роутинга и витрины (/agents, /v1/models)."""

    name: str
    title: str
    description: str
    sensitivity: DataSensitivity
    models: list[str]
    agent: Agent[AgentDeps, str]


REGISTRY: dict[str, AgentCard] = {
    kolobok.NAME: AgentCard(
        name=kolobok.NAME,
        title=kolobok.TITLE,
        description="Общий помощник: ресёрч, поиск, бытовые вопросы.",
        sensitivity=kolobok.SENSITIVITY,
        models=kolobok.MODELS,
        agent=kolobok.agent,
    ),
    koschei.NAME: AgentCard(
        name=koschei.NAME,
        title=koschei.TITLE,
        description="SecOps: обучение ИБ, threat modeling, hardening своей инфры.",
        sensitivity=koschei.SENSITIVITY,
        models=koschei.MODELS,
        agent=koschei.agent,
    ),
    levsha.NAME: AgentCard(
        name=levsha.NAME,
        title=levsha.TITLE,
        description="Coder: чтение, написание и ревью кода в репозиториях.",
        sensitivity=levsha.SENSITIVITY,
        models=levsha.MODELS,
        agent=levsha.agent,
    ),
    ded.NAME: AgentCard(
        name=ded.NAME,
        title=ded.TITLE,
        description="Летописец: ведёт хронику комбайна и проектов, пересказывает события.",
        sensitivity=ded.SENSITIVITY,
        models=ded.MODELS,
        agent=ded.agent,
    ),
}

DEFAULT_AGENT = kolobok.NAME


def get_agent(name: str | None) -> AgentCard:
    """Вернуть карточку агента по имени (или дефолтного Колобка).

    Имя нечувствительно к регистру; неизвестное имя -> дефолтный агент,
    чтобы OpenWebUI с произвольной моделью не падал.
    """
    if not name:
        return REGISTRY[DEFAULT_AGENT]
    return REGISTRY.get(name.strip().lower(), REGISTRY[DEFAULT_AGENT])

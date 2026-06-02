"""Реестр агентов: единая точка, откуда API берёт агента по имени.

Этап 2 — реализован только Колобок. Кощей и Левша добавляются на Этапе 4,
тогда же сюда дописываются их `AgentCard`.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent

from . import kolobok
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

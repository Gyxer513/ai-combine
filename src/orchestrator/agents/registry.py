"""Реестр агентов: единая точка, откуда API берёт агента по имени.

Все четверо (assistant / recon / coder / planner) зарегистрированы и переключаются
как отдельные «модели» в OpenWebUI. Специфичные инструменты (RAG, sandbox, GitHub,
Deck-планировщик) навешиваются в модулях самих агентов.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent

from . import assistant, coder, planner, recon
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
    assistant.NAME: AgentCard(
        name=assistant.NAME,
        title=assistant.TITLE,
        description="Общий помощник: ресёрч, поиск, бытовые вопросы.",
        sensitivity=assistant.SENSITIVITY,
        models=assistant.MODELS,
        agent=assistant.agent,
    ),
    recon.NAME: AgentCard(
        name=recon.NAME,
        title=recon.TITLE,
        description="SecOps: обучение ИБ, threat modeling, hardening своей инфры.",
        sensitivity=recon.SENSITIVITY,
        models=recon.MODELS,
        agent=recon.agent,
    ),
    coder.NAME: AgentCard(
        name=coder.NAME,
        title=coder.TITLE,
        description="Coder: чтение, написание и ревью кода в репозиториях.",
        sensitivity=coder.SENSITIVITY,
        models=coder.MODELS,
        agent=coder.agent,
    ),
    planner.NAME: AgentCard(
        name=planner.NAME,
        title=planner.TITLE,
        description="Планировщик: режет ТЗ проекта на дочерние задачи для агентов.",
        sensitivity=planner.SENSITIVITY,
        models=planner.MODELS,
        agent=planner.agent,
    ),
}

DEFAULT_AGENT = assistant.NAME


def get_agent(name: str | None) -> AgentCard:
    """Вернуть карточку агента по имени (или дефолтного assistant).

    Имя нечувствительно к регистру; неизвестное имя -> дефолтный агент,
    чтобы OpenWebUI с произвольной моделью не падал.
    """
    if not name:
        return REGISTRY[DEFAULT_AGENT]
    return REGISTRY.get(name.strip().lower(), REGISTRY[DEFAULT_AGENT])

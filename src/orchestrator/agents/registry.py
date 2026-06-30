"""Agent registry: the single place the API uses to look up an agent by name.

All four (assistant / recon / coder / planner) are registered and switched
between as separate "models" in OpenWebUI. Specific tools (RAG, sandbox, GitHub,
Deck planner) are attached in the agents' own modules.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent

from . import assistant, coder, planner, recon
from .base import AgentDeps, DataSensitivity


@dataclass(frozen=True, slots=True)
class AgentCard:
    """Agent metadata for routing and display (/agents, /v1/models)."""

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
        description="General assistant: research, search, everyday questions.",
        sensitivity=assistant.SENSITIVITY,
        models=assistant.MODELS,
        agent=assistant.agent,
    ),
    recon.NAME: AgentCard(
        name=recon.NAME,
        title=recon.TITLE,
        description="SecOps: infosec learning, threat modeling, hardening your own infra.",
        sensitivity=recon.SENSITIVITY,
        models=recon.MODELS,
        agent=recon.agent,
    ),
    coder.NAME: AgentCard(
        name=coder.NAME,
        title=coder.TITLE,
        description="Coder: reading, writing, and reviewing code in repositories.",
        sensitivity=coder.SENSITIVITY,
        models=coder.MODELS,
        agent=coder.agent,
    ),
    planner.NAME: AgentCard(
        name=planner.NAME,
        title=planner.TITLE,
        description="Planner: splits a project spec into subtasks for the agents.",
        sensitivity=planner.SENSITIVITY,
        models=planner.MODELS,
        agent=planner.agent,
    ),
}

DEFAULT_AGENT = assistant.NAME


def get_agent(name: str | None) -> AgentCard:
    """Return an agent card by name (or the default assistant).

    The name is case-insensitive; an unknown name -> the default agent,
    so OpenWebUI doesn't break when given an arbitrary model.
    """
    if not name:
        return REGISTRY[DEFAULT_AGENT]
    return REGISTRY.get(name.strip().lower(), REGISTRY[DEFAULT_AGENT])

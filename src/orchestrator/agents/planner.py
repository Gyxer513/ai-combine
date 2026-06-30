"""🧭 Planner — Orchestrator Agent.

Takes a project spec and splits it into subtasks for the other agents
(recon / coder / assistant), laying them out as cards on a Deck task board — where
the deck-worker picks them up. Planning requires strong reasoning, so the primary
model is `qwen-max`, with `qwen-plus` as backup. Sensitivity INTERNAL
(a spec may contain private project context).
"""

from __future__ import annotations

from pydantic_ai import Agent

from ..tools.common import register_common_tools
from ..tools.deck import register_planner_tool
from ..tools.rag import register_rag_tool
from .base import (
    AgentDeps,
    DataSensitivity,
    build_model,
    history_capabilities,
    load_prompt,
)

NAME = "planner"
TITLE = "🧭 Planner"
SENSITIVITY = DataSensitivity.INTERNAL

# Decomposition = reasoning: qwen-max primary, qwen-plus backup.
MODELS = ["qwen-max", "qwen-plus"]

agent = Agent(
    build_model(MODELS),
    deps_type=AgentDeps,
    instructions=load_prompt(NAME),  # see the explanation in assistant.py
    name=NAME,
    capabilities=history_capabilities(),
)
register_common_tools(agent)
register_rag_tool(agent, namespace="personal")
register_planner_tool(agent)  # slice_project: subtask cards onto the Deck board

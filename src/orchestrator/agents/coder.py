"""🔨 Coder — Coder Agent.

Working with repositories: reading, writing, and reviewing code. Sensitivity INTERNAL
(private code does not leak into cloaked models). Model: nemotron-super-free (top
free model on SWE-Bench), backups qwen-coder → qwen-max.

Tools: GitHub (RW) and sandboxed bash (tests/linters, no network).
"""

from __future__ import annotations

from pydantic_ai import Agent

from ..tools.common import register_common_tools
from ..tools.github import register_github_tools
from ..tools.guard import CODER_ALLOWED
from ..tools.rag import register_rag_tool
from ..tools.shell import register_shell_tool
from .base import (
    AgentDeps,
    DataSensitivity,
    build_model,
    history_capabilities,
    load_prompt,
)

NAME = "coder"
TITLE = "🔨 Coder"
SENSITIVITY = DataSensitivity.INTERNAL

# nemotron-super-free (top free model on SWE-Bench), backups qwen-coder → qwen-max.
# INTERNAL: private code — open weights / Alibaba, no cloaked owl.
MODELS = ["nemotron-super-free", "qwen-coder", "qwen-max"]

agent = Agent(
    build_model(MODELS),
    deps_type=AgentDeps,
    instructions=load_prompt(NAME),  # see the explanation in assistant.py
    name=NAME,
    capabilities=history_capabilities(),  # history compaction by token budget
)
register_common_tools(agent)
register_rag_tool(agent, namespace="coding")
register_shell_tool(
    agent,
    profile="coder",  # broker: network OFF for running code
    allowed=CODER_ALLOWED,  # interpreters ok: sandbox without network, no exfiltration
    name="run_shell",
    what="Run code/tests/linters",
    network_note="NO network",
)
register_github_tools(agent)  # GitHub repositories: read, commit to a branch, PR

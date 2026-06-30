"""🛡 Recon — SecOps Agent.

Infosec learning, threat modeling, defensive coding, hardening your own infra.
Data sensitivity SECRET — enterprise/paid models only, no cloaked ones. The primary
model is `glm-5.1` (MaaS workspace, thinking on), with `qwen-max` as backup.

RAG namespace `security`; security commands run in the isolated sandbox-broker.
"""

from __future__ import annotations

from pydantic_ai import Agent

from ..tools.common import register_common_tools
from ..tools.guard import SECOPS_ALLOWED
from ..tools.rag import register_rag_tool
from ..tools.shell import register_shell_tool
from .base import (
    AgentDeps,
    DataSensitivity,
    build_model,
    history_capabilities,
    load_prompt,
)

NAME = "recon"
TITLE = "🛡 Recon"
SENSITIVITY = DataSensitivity.SECRET

# glm-5.1 (thinking) primary, backups nemotron-super-free (open weights) → qwen-max.
# SECRET: no cloaked models — owl-alpha is excluded.
MODELS = ["glm-5.1", "nemotron-super-free", "qwen-max"]

agent = Agent(
    build_model(MODELS),
    deps_type=AgentDeps,
    instructions=load_prompt(NAME),  # see the explanation in assistant.py
    name=NAME,
    capabilities=history_capabilities(),  # history compaction by token budget
)
register_common_tools(agent)
register_rag_tool(agent, namespace="security")
register_shell_tool(
    agent,
    profile="secops",  # broker: network ON to scan your own infra
    allowed=SECOPS_ALLOWED,  # no interpreters: network + arbitrary exec = exfiltration
    name="run_security_command",
    what="Run a security command (nmap, openssl, dig, curl, nc)",
    network_note="network available",
)

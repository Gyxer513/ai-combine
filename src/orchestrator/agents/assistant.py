"""💬 Assistant — General Agent.

General assistant: research, search, everyday questions. Data sensitivity PUBLIC,
so free models come first: primary `owl-alpha-free` (1M context),
backups `qwen-plus` → `qwen-max`.

Tools: web_search, scratchpad memory, RAG (`search_knowledge_base`).
"""

from __future__ import annotations

from pydantic_ai import Agent

from ..tools.common import register_common_tools
from ..tools.docs import register_docs_tool
from ..tools.rag import register_rag_tool
from .base import (
    AgentDeps,
    DataSensitivity,
    build_model,
    history_capabilities,
    load_prompt,
)

NAME = "assistant"
TITLE = "💬 Assistant"
SENSITIVITY = DataSensitivity.PUBLIC

# LiteLLM chain: primary + fallbacks.
MODELS = ["owl-alpha-free", "qwen-plus", "qwen-max"]

agent = Agent(
    build_model(MODELS),
    deps_type=AgentDeps,
    # instructions (not system_prompt): applied on EVERY run, including when
    # message_history is passed (multi-turn /chat, the OpenWebUI path). With system_prompt
    # the persona was lost on the second+ turn and in OpenWebUI.
    instructions=load_prompt(NAME),
    name=NAME,
    capabilities=history_capabilities(),  # history compaction by token budget
)
register_common_tools(agent)
register_rag_tool(agent, namespace="personal")
register_docs_tool(agent)  # semantic search over the combine's own docs

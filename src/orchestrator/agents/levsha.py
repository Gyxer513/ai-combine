"""🔨 Левша — Coder Agent.

Работа с репозиториями: чтение кода, написание, ревью. Чувствительность INTERNAL
(приватный код не уходит в cloaked-модели). По плану модели маршрутизируются по
подзадаче (planner/coder/reviewer); на Этапе 2 берём кодовую модель Alibaba.

Этап 2: общие инструменты (web_search, память). Gitea (RW) и sandboxed bash
для тестов/линтеров — Этап 6.
"""

from __future__ import annotations

from pydantic_ai import Agent

from ..tools.common import register_common_tools
from ..tools.guard import CODER_ALLOWED
from ..tools.rag import register_rag_tool
from ..tools.shell import register_shell_tool
from .base import AgentDeps, DataSensitivity, build_model, load_prompt

NAME = "levsha"
TITLE = "🔨 Левша"
SENSITIVITY = DataSensitivity.INTERNAL

# План (Левша-code): nemotron-super-free (топ SWE-Bench free), резерв qwen-coder → qwen-max.
# INTERNAL: приватный код — open weights / Alibaba, без cloaked owl.
MODELS = ["nemotron-super-free", "qwen-coder", "qwen-max"]

agent = Agent(
    build_model(MODELS),
    deps_type=AgentDeps,
    instructions=load_prompt(NAME),  # см. пояснение в kolobok.py
    name=NAME,
)
register_common_tools(agent)
register_rag_tool(agent, namespace="coding")
register_shell_tool(
    agent,
    network=False,  # прогон кода/тестов — без сети
    name="run_shell",
    what="Запуск кода/тестов/линтеров",
    allowed=CODER_ALLOWED,  # интерпретаторы ок: sandbox без сети, эксфил невозможен
)

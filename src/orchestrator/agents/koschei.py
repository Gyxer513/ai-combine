"""🦴 Кощей — SecOps Agent.

Обучение ИБ, threat modeling, defensive coding, hardening собственной инфры.
Чувствительность данных SECRET — только enterprise/платные модели, никаких
cloaked. Основная модель по плану — `glm-5.1` (MaaS workspace, thinking on),
резерв `qwen-max`.

Этап 2: общие инструменты (web_search, память). RAG namespace `security`
(Этап 3) и sandboxed bash (Этап 6) добавятся позже.
"""

from __future__ import annotations

from pydantic_ai import Agent

from ..tools.common import register_common_tools
from ..tools.guard import SECOPS_ALLOWED
from ..tools.rag import register_rag_tool
from ..tools.shell import register_shell_tool
from .base import AgentDeps, DataSensitivity, build_model, load_prompt

NAME = "koschei"
TITLE = "🦴 Кощей"
SENSITIVITY = DataSensitivity.SECRET

# План (Кощей): glm-5.1 (thinking) основной, резерв nemotron-super-free (open weights) → qwen-max.
# SECRET: никаких cloaked-моделей — owl-alpha исключён.
MODELS = ["glm-5.1", "nemotron-super-free", "qwen-max"]

agent = Agent(
    build_model(MODELS),
    deps_type=AgentDeps,
    instructions=load_prompt(NAME),  # см. пояснение в kolobok.py
    name=NAME,
)
register_common_tools(agent)
register_rag_tool(agent, namespace="security")
register_shell_tool(
    agent,
    profile="secops",  # у брокера: сеть ВКЛ для скана своей инфры
    allowed=SECOPS_ALLOWED,  # без интерпретаторов: сеть + произвольный exec = эксфил
    name="run_security_command",
    what="Запуск security-команды (nmap, openssl, dig, curl, nc)",
    network_note="есть сеть",
)

"""Базовый слой агентов (Pydantic AI).

Здесь общая инфраструктура, не зависящая от конкретного агента:

* `DataSensitivity` — категория данных агента (см. план: выбор моделей).
* `build_model` — фабрика модели поверх LiteLLM с пер-агентной fallback-цепочкой
  (`FallbackModel`): первая модель основная, остальные — резерв при сбое/лимите.
* `load_prompt` — чтение системного промпта из `prompts/<name>.md`.
* `AgentDeps` — общие зависимости, прокидываемые в инструменты через `RunContext`.

Сами агенты (Колобок/Кощей/Левша) собираются в своих модулях.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from ..config import settings
from ..rag.embedder import EmbeddingClient
from ..rag.store import VectorStore
from ..tools.guard import UNTRUSTED_PREAMBLE
from ..tools.memory import ConversationStore
from ..tools.shell import BrokerClient
from ..tools.web_search import WebSearchClient
from .history import compact_history

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class DataSensitivity(StrEnum):
    """Категория данных агента -> допустимость cloaked-моделей (см. план)."""

    PUBLIC = "public"  # любые free-модели
    INTERNAL = "internal"  # только open weights / платные
    SECRET = "secret"  # только платные / enterprise (Кощей)


def history_capabilities() -> list[ProcessHistory]:
    """Capabilities ужимания истории — единые для всех агентов (см. history.py)."""
    return [ProcessHistory(compact_history)]


def load_prompt(name: str) -> str:
    """Прочитать системный промпт `prompts/<name>.md` + добавить security-преамбулу.

    Преамбула (защита от prompt injection) дописывается ко всем агентам
    централизованно — чтобы Колобок/Кощей/Левша/будущий ДЕД одинаково не доверяли
    инструкциям, спрятанным в результатах инструментов.
    """
    path = PROMPTS_DIR / f"{name}.md"
    persona = path.read_text(encoding="utf-8").strip()
    return f"{persona}\n\n{UNTRUSTED_PREAMBLE}"


def build_model(model_names: list[str]) -> Model:
    """Собрать модель поверх LiteLLM из цепочки имён моделей.

    `model_names` — имена deployment'ов из `litellm_config.yaml` (например
    ``["owl-alpha-free", "qwen-plus", "qwen-max"]``). Первая — основная, на сбое
    или rate-limit Pydantic AI прозрачно переключается на следующую.
    """
    if not model_names:
        raise ValueError("model_names не может быть пустым")

    provider = OpenAIProvider(
        base_url=settings.litellm_base_url,
        api_key=settings.litellm_master_key,
    )
    models = [OpenAIChatModel(name, provider=provider) for name in model_names]
    if len(models) == 1:
        return models[0]
    return FallbackModel(*models)


@dataclass(slots=True)
class AgentDeps:
    """Зависимости, доступные инструментам агента через `RunContext`.

    Создаётся на время одного запроса. `conversation_id` связывает вызов
    с историей и scratchpad-заметками в общем `ConversationStore`.
    `embedder`/`vstore` нужны инструменту RAG (None — если RAG не сконфигурирован).
    """

    conversation_id: str
    web: WebSearchClient
    store: ConversationStore
    embedder: EmbeddingClient | None = None
    vstore: VectorStore | None = None
    broker: BrokerClient | None = None  # клиент sandbox-broker (shell-инструменты)
    extra: dict[str, str] = field(default_factory=dict)


@lru_cache(maxsize=1)
def shared_store() -> ConversationStore:
    """Единый на процесс стор истории/заметок (Этап 2 — in-memory)."""
    return ConversationStore()


@lru_cache(maxsize=1)
def shared_vstore() -> VectorStore:
    """Единое на процесс подключение к Qdrant."""
    return VectorStore()

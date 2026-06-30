"""Base agent layer (Pydantic AI).

Shared infrastructure that does not depend on any specific agent:

* `DataSensitivity` — an agent's data category (see the plan: model selection).
* `build_model` — a model factory on top of LiteLLM with a per-agent fallback chain
  (`FallbackModel`): the first model is primary, the rest are backups on failure/limit.
* `load_prompt` — reads the system prompt from `prompts/<name>.md`.
* `AgentDeps` — shared dependencies passed into tools via `RunContext`.

The agents themselves (assistant/recon/coder) are assembled in their own modules.
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
from ..persistence import shared_db
from ..rag.embedder import EmbeddingClient
from ..rag.store import VectorStore
from ..tools.github import GitHubClient
from ..tools.guard import UNTRUSTED_PREAMBLE
from ..tools.memory import ConversationStore
from ..tools.shell import BrokerClient
from ..tools.web_search import WebSearchClient
from .history import compact_history

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class DataSensitivity(StrEnum):
    """Agent data category -> whether cloaked models are allowed (see the plan)."""

    PUBLIC = "public"  # any free model
    INTERNAL = "internal"  # open weights / paid only
    SECRET = "secret"  # paid / enterprise only (recon)


def history_capabilities() -> list[ProcessHistory]:
    """History-compaction capabilities — shared by all agents (see history.py)."""
    return [ProcessHistory(compact_history)]


def load_prompt(name: str) -> str:
    """Read the system prompt `prompts/<name>.md` and append the security preamble.

    The preamble (prompt-injection defense) is appended to every agent
    centrally — so assistant/recon/coder/the future planner all equally distrust
    instructions hidden inside tool results.
    """
    path = PROMPTS_DIR / f"{name}.md"
    persona = path.read_text(encoding="utf-8").strip()
    return f"{persona}\n\n{UNTRUSTED_PREAMBLE}"


def build_model(model_names: list[str]) -> Model:
    """Build a model on top of LiteLLM from a chain of model names.

    `model_names` — deployment names from `litellm_config.yaml` (for example
    ``["owl-alpha-free", "qwen-plus", "qwen-max"]``). The first is primary; on failure
    or rate-limit Pydantic AI transparently switches to the next.
    """
    if not model_names:
        raise ValueError("model_names cannot be empty")

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
    """Dependencies available to an agent's tools via `RunContext`.

    Created for the duration of a single request. `conversation_id` links the call
    to its history and scratchpad notes in the shared `ConversationStore`.
    `embedder`/`vstore` are needed by the RAG tool (None if RAG is not configured).
    """

    conversation_id: str
    web: WebSearchClient
    store: ConversationStore
    embedder: EmbeddingClient | None = None
    vstore: VectorStore | None = None
    broker: BrokerClient | None = None  # sandbox-broker client (shell tools)
    github: GitHubClient | None = None  # GitHub client (repositories, coder)
    extra: dict[str, str] = field(default_factory=dict)


@lru_cache(maxsize=1)
def shared_store() -> ConversationStore:
    """Process-wide history/notes store (SQLite, survives restarts)."""
    return ConversationStore(shared_db())


@lru_cache(maxsize=1)
def shared_vstore() -> VectorStore:
    """Process-wide connection to Qdrant."""
    return VectorStore()

"""HTTP-роуты оркестратора.

Два набора эндпоинтов:

* Нативный — `/agents`, `/chat` (многоходовой по `conversation_id`).
* OpenAI-совместимый — `/v1/models`, `/v1/chat/completions` (stream + non-stream),
  чтобы OpenWebUI ходил в оркестратор как в обычный OpenAI-бэкенд, а оркестратор
  уже выбирал агента по имени модели и сам звал LiteLLM.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from ..agents.base import AgentDeps, shared_store, shared_vstore
from ..agents.registry import REGISTRY, get_agent
from ..rag.embedder import EmbeddingClient
from ..tools.web_search import WebSearchClient
from .schemas import (
    AgentInfo,
    ChatRequest,
    ChatResponse,
    OpenAIChatRequest,
    OpenAIMessage,
)

log = structlog.get_logger()
router = APIRouter()


def _build_deps(request: Request, conversation_id: str) -> AgentDeps:
    """Собрать зависимости агента на один запрос."""
    http = request.app.state.http
    return AgentDeps(
        conversation_id=conversation_id,
        web=WebSearchClient(http),
        store=shared_store(),
        embedder=EmbeddingClient(http),
        vstore=shared_vstore(),
    )


@router.get("/agents", response_model=list[AgentInfo])
async def list_agents() -> list[AgentInfo]:
    """Список доступных агентов."""
    return [
        AgentInfo(
            name=c.name,
            title=c.title,
            description=c.description,
            sensitivity=str(c.sensitivity),
            models=c.models,
        )
        for c in REGISTRY.values()
    ]


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> ChatResponse:
    """Один ход диалога с агентом. История подтягивается по `conversation_id`."""
    card = get_agent(req.agent)
    conversation_id = req.conversation_id or uuid.uuid4().hex
    store = shared_store()
    deps = _build_deps(request, conversation_id)

    result = await card.agent.run(
        req.message,
        deps=deps,
        message_history=store.history(conversation_id),
    )
    store.extend_history(conversation_id, result.new_messages())
    log.info("chat.done", agent=card.name, conversation_id=conversation_id)

    return ChatResponse(
        agent=card.name,
        conversation_id=conversation_id,
        reply=result.output,
    )


# --- OpenAI-совместимый слой ---


def _to_history(messages: list[OpenAIMessage]) -> tuple[str, list[ModelMessage]]:
    """Разложить OpenAI-сообщения на (последний промпт, история).

    Системные сообщения отбрасываем — у агента собственный системный промпт.
    Последнее user-сообщение становится промптом текущего хода, остальное —
    историей в формате Pydantic AI.
    """
    prompt = ""
    history: list[ModelMessage] = []
    for msg in messages:
        if msg.role == "user":
            if prompt:
                history.append(ModelRequest(parts=[UserPromptPart(content=prompt)]))
            prompt = msg.content
        elif msg.role == "assistant":
            if prompt:
                history.append(ModelRequest(parts=[UserPromptPart(content=prompt)]))
                prompt = ""
            history.append(ModelResponse(parts=[TextPart(content=msg.content)]))
        # system / tool — пропускаем
    return prompt, history


def _completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex}"


@router.get("/v1/models")
async def openai_models() -> dict:
    """OpenAI-совместимый список моделей: по одной «модели» на агента."""
    created = int(time.time())
    return {
        "object": "list",
        "data": [
            {"id": name, "object": "model", "created": created, "owned_by": "ai-combine"}
            for name in REGISTRY
        ],
    }


@router.post("/v1/chat/completions")
async def openai_chat_completions(req: OpenAIChatRequest, request: Request):
    """OpenAI-совместимый чат. `model` выбирает агента."""
    card = get_agent(req.model)
    prompt, history = _to_history(req.messages)
    if not prompt:
        prompt = "(пустой запрос)"
    deps = _build_deps(request, conversation_id=uuid.uuid4().hex)
    completion_id = _completion_id()
    created = int(time.time())

    if req.stream:
        return StreamingResponse(
            _stream_completion(card, prompt, history, deps, completion_id, created, req.model),
            media_type="text/event-stream",
        )

    result = await card.agent.run(prompt, deps=deps, message_history=history)
    log.info("openai.chat.done", agent=card.name, stream=False)
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": result.output},
                "finish_reason": "stop",
            }
        ],
        "usage": _usage_dict(result.usage),
    }


async def _stream_completion(
    card,
    prompt: str,
    history: list[ModelMessage],
    deps: AgentDeps,
    completion_id: str,
    created: int,
    model: str,
) -> AsyncIterator[str]:
    """Генерировать SSE-чанки в формате OpenAI chat.completion.chunk."""

    def chunk(delta: dict, finish: str | None) -> str:
        payload = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    yield chunk({"role": "assistant"}, None)
    try:
        async with card.agent.run_stream(prompt, deps=deps, message_history=history) as result:
            async for delta in result.stream_text(delta=True):
                yield chunk({"content": delta}, None)
    except Exception as exc:  # noqa: BLE001 — в стрим уже нельзя вернуть HTTP-ошибку
        log.warning("openai.chat.stream_failed", agent=card.name, error=str(exc))
        yield chunk({"content": f"\n[ошибка: {exc}]"}, None)
    yield chunk({}, "stop")
    yield "data: [DONE]\n\n"


def _usage_dict(usage) -> dict:
    """Best-effort извлечение токенов из RunUsage Pydantic AI."""
    prompt_tokens = getattr(usage, "input_tokens", None) or 0
    completion_tokens = getattr(usage, "output_tokens", None) or 0
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }

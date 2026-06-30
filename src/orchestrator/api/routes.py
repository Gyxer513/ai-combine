"""Orchestrator HTTP routes.

Two sets of endpoints:

* Native — `/agents`, `/chat` (multi-turn by `conversation_id`).
* OpenAI-compatible — `/v1/models`, `/v1/chat/completions` (stream + non-stream),
  so OpenWebUI talks to the orchestrator like an ordinary OpenAI backend, while the
  orchestrator selects an agent by model name and calls LiteLLM itself.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request
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
from ..config import settings
from ..metrics import shared_metrics
from ..rag.embedder import EmbeddingClient
from ..tools.github import GitHubClient
from ..tools.shell import BrokerClient
from ..tools.web_search import WebSearchClient
from .schemas import (
    AgentInfo,
    ChatRequest,
    ChatResponse,
    OpenAIChatRequest,
    OpenAIMessage,
)

log = structlog.get_logger()


async def require_token(authorization: str | None = Header(default=None)) -> None:
    """Verify the Bearer token. An empty token in the config means no enforcement (see the
    startup warning + bind localhost). Protects the agent-invoking endpoints."""
    token = settings.orchestrator_api_token
    if not token:
        return
    if authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="invalid or missing API token")


# All agent-invoking routes are token-protected (see require_token). /health is open.
router = APIRouter(dependencies=[Depends(require_token)])


def _build_deps(request: Request, conversation_id: str) -> AgentDeps:
    """Build per-request agent dependencies."""
    http = request.app.state.http
    return AgentDeps(
        conversation_id=conversation_id,
        web=WebSearchClient(http),
        store=shared_store(),
        embedder=EmbeddingClient(http),
        vstore=shared_vstore(),
        broker=BrokerClient(http),
        github=GitHubClient(http),
    )


@router.get("/agents", response_model=list[AgentInfo])
async def list_agents() -> list[AgentInfo]:
    """List the available agents."""
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
    """One conversation turn with an agent. History is pulled by `conversation_id`."""
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
    _record(card.name, result.usage)
    log.info("chat.done", agent=card.name, conversation_id=conversation_id)

    return ChatResponse(
        agent=card.name,
        conversation_id=conversation_id,
        reply=result.output,
    )


# --- OpenAI-compatible layer ---


def _to_history(messages: list[OpenAIMessage]) -> tuple[str, list[ModelMessage]]:
    """Split OpenAI messages into (last prompt, history).

    System messages are dropped — the agent has its own system prompt.
    The last user message becomes the current turn's prompt; the rest become
    history in Pydantic AI format.
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
        # system / tool — skipped
    return prompt, history


def _completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex}"


@router.get("/v1/models")
async def openai_models() -> dict:
    """OpenAI-compatible model list: one "model" per agent."""
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
    """OpenAI-compatible chat. `model` selects the agent."""
    card = get_agent(req.model)
    prompt, history = _to_history(req.messages)
    if not prompt:
        prompt = "(empty request)"
    deps = _build_deps(request, conversation_id=uuid.uuid4().hex)
    completion_id = _completion_id()
    created = int(time.time())

    if req.stream:
        return StreamingResponse(
            _stream_completion(card, prompt, history, deps, completion_id, created, req.model),
            media_type="text/event-stream",
        )

    result = await card.agent.run(prompt, deps=deps, message_history=history)
    _record(card.name, result.usage)
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
    """Generate SSE chunks in the OpenAI chat.completion.chunk format."""

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
            _record(card.name, result.usage)
    except Exception as exc:  # noqa: BLE001 — can no longer return an HTTP error mid-stream
        log.warning("openai.chat.stream_failed", agent=card.name, error=str(exc))
        yield chunk({"content": f"\n[error: {exc}]"}, None)
    yield chunk({}, "stop")
    yield "data: [DONE]\n\n"


def _tokens(usage) -> tuple[int, int]:
    """(input, output) tokens from Pydantic AI RunUsage (`result.usage` is a property)."""
    return int(getattr(usage, "input_tokens", 0) or 0), int(getattr(usage, "output_tokens", 0) or 0)


def _usage_dict(usage) -> dict:
    """OpenAI-compatible usage block."""
    prompt_tokens, completion_tokens = _tokens(usage)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def _record(agent: str, usage) -> None:
    """Record the request in the dashboard metrics (best-effort, never breaks the response)."""
    try:
        inp, out = _tokens(usage)
        shared_metrics().record(agent, inp, out)
    except Exception:  # noqa: BLE001 — metrics must not affect the response
        shared_metrics().record(agent, 0, 0)

"""Pydantic schemas for the HTTP layer: native /chat and OpenAI-compatible /v1."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# --- Native orchestrator API ---


class ChatRequest(BaseModel):
    """A /chat request. `conversation_id` ties replies into a multi-turn conversation."""

    message: str = Field(min_length=1)
    agent: str | None = None
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    agent: str
    conversation_id: str
    reply: str


class AgentInfo(BaseModel):
    name: str
    title: str
    description: str
    sensitivity: str
    models: list[str]


# --- OpenAI-compatible layer (for OpenWebUI) ---


class OpenAIMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""


class OpenAIChatRequest(BaseModel):
    model: str
    messages: list[OpenAIMessage]
    stream: bool = False
    # other OpenAI fields (temperature, etc.) are ignored — extra is allowed
    model_config = {"extra": "allow"}

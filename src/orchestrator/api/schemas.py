"""Pydantic-схемы HTTP-слоя: нативный /chat и OpenAI-совместимый /v1."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# --- Нативный API оркестратора ---


class ChatRequest(BaseModel):
    """Запрос к /chat. `conversation_id` связывает реплики в многоходовой диалог."""

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


# --- OpenAI-совместимый слой (для OpenWebUI) ---


class OpenAIMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""


class OpenAIChatRequest(BaseModel):
    model: str
    messages: list[OpenAIMessage]
    stream: bool = False
    # прочие поля OpenAI (temperature и т.п.) игнорируем — extra разрешён
    model_config = {"extra": "allow"}

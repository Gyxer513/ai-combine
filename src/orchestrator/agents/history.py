"""Conversation history compaction before a model request.

`compact_history` is a processor for Pydantic AI `ProcessHistory`: it runs before
EVERY model request on both paths (Telegram `/chat` and OpenWebUI `/v1`) and keeps
the history within the token budget. The system prompt (`instructions=`) is passed
separately and is not touched here.

Strategy — a deterministic budget-based window (no LLM call):
* estimate approximate tokens, and if it fits — return it as is;
* otherwise keep the tail (the most recent messages) within budget;
* shift the window's start to a "clean" user request, so we don't leave an orphaned
  tool-return without its tool-call (otherwise the provider complains);
* if anything was cut — prepend an honest truncation note at the start.

LLM summarization of the old tail is deliberately NOT done: on the stateless
OpenWebUI path it would be recomputed every turn (the client sends the full history) —
wasted money without caching. We'll revisit it once state is persisted by conversation_id.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    SystemPromptPart,
    ToolReturnPart,
    UserPromptPart,
)

from ..config import settings

_TRIM_MARKER = (
    "[To the system: the early part of this conversation was collapsed to save context. "
    "If you need details from the start of the conversation, ask the user to recap.]"
)

# Rough estimate: ~4 characters per token + overhead for message framing.
_CHARS_PER_TOKEN = 4
_MSG_OVERHEAD_TOKENS = 4


def _content_text(content: object) -> str:
    """Extract text from a content part (a string or a list of multimodal pieces)."""
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence):
        return " ".join(c for c in content if isinstance(c, str))
    return str(content)


def _part_text(part: object) -> str:
    """Text representation of a single message part for size estimation."""
    content = getattr(part, "content", None)
    if content is not None:
        return _content_text(content)
    args = getattr(part, "args", None)  # ToolCallPart
    if args is not None:
        return args if isinstance(args, str) else str(args)
    return str(part)


def _message_tokens(msg: ModelMessage) -> int:
    """Approximate token count of a single message."""
    chars = sum(len(_part_text(p)) for p in msg.parts)
    return chars // _CHARS_PER_TOKEN + _MSG_OVERHEAD_TOKENS


def _is_clean_user_request(msg: ModelMessage) -> bool:
    """A ModelRequest with user input and WITHOUT a tool-return.

    Such a message is safe to make first in the window: it doesn't reference a
    previous (possibly cut) tool-call.
    """
    if not isinstance(msg, ModelRequest):
        return False
    has_user = any(isinstance(p, (UserPromptPart, SystemPromptPart)) for p in msg.parts)
    has_tool_return = any(isinstance(p, ToolReturnPart) for p in msg.parts)
    return has_user and not has_tool_return


def _with_marker(first: ModelMessage) -> list[ModelMessage]:
    """Return the window's starting message(s) with the truncation note added.

    If the first message is a ModelRequest, embed the note into it (so we don't add
    an extra turn). Otherwise, place the note as a separate request before it.
    """
    marker = UserPromptPart(content=_TRIM_MARKER)
    if isinstance(first, ModelRequest):
        return [ModelRequest(parts=[marker, *first.parts])]
    return [ModelRequest(parts=[marker]), first]


async def compact_history(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Compact the history down to the token budget (see the module docstring)."""
    if not messages:
        return messages

    budget = settings.history_max_tokens
    if sum(_message_tokens(m) for m in messages) <= budget:
        return messages

    # Collect the tail within budget (at least the last message — always).
    kept: list[ModelMessage] = []
    used = 0
    for msg in reversed(messages):
        tokens = _message_tokens(msg)
        if kept and used + tokens > budget:
            break
        kept.append(msg)
        used += tokens
    kept.reverse()

    # Shift the window's start to a "clean" user request.
    while len(kept) > 1 and not _is_clean_user_request(kept[0]):
        kept.pop(0)

    if len(kept) == len(messages):  # nothing was actually cut
        return messages

    return [*_with_marker(kept[0]), *kept[1:]]

"""Conversation history compaction tests (agents/history.py)."""

from __future__ import annotations

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from src.orchestrator.agents.history import _TRIM_MARKER, compact_history
from src.orchestrator.config import settings


def _user(text: str) -> ModelRequest:
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _assistant(text: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(content=text)])


def _first_text(msg) -> str:
    return "".join(getattr(p, "content", "") for p in msg.parts if isinstance(p, UserPromptPart))


async def test_under_budget_unchanged():
    msgs = [_user("hi"), _assistant("hello")]
    out = await compact_history(list(msgs))
    assert out == msgs


async def test_empty_unchanged():
    assert await compact_history([]) == []


async def test_over_budget_trims_to_tail(monkeypatch):
    monkeypatch.setattr(settings, "history_max_tokens", 50)
    # each message ~ (200//4 + 4) = 54 tokens -> only the tail fits the budget
    big = "x" * 200
    msgs = [_user(big), _assistant(big), _user(big), _assistant(big), _user("fresh question")]
    out = await compact_history(msgs)
    assert len(out) < len(msgs)
    # the last user request is kept (the marker is embedded in the same message)
    assert any("fresh question" in _first_text(m) for m in out if isinstance(m, ModelRequest))
    # at the start — the truncation note
    assert _TRIM_MARKER in _first_text(out[0])


async def test_window_does_not_start_with_tool_return(monkeypatch):
    monkeypatch.setattr(settings, "history_max_tokens", 30)
    big = "y" * 200
    # tool loop: assistant calls a tool -> request with tool-return -> final
    msgs = [
        _user(big),
        ModelResponse(parts=[ToolCallPart(tool_name="t", args="{}", tool_call_id="1")]),
        ModelRequest(parts=[ToolReturnPart(tool_name="t", content=big, tool_call_id="1")]),
        _user("final question"),
    ]
    out = await compact_history(msgs)
    # the window's first message is a clean user-request (with marker), no tool-return
    assert isinstance(out[0], ModelRequest)
    assert any(isinstance(p, UserPromptPart) for p in out[0].parts)
    # the orphaned tool-return (without its tool-call) is dropped from the window entirely
    assert not any(isinstance(p, ToolReturnPart) for m in out for p in m.parts)


async def test_keeps_last_message_even_if_huge(monkeypatch):
    monkeypatch.setattr(settings, "history_max_tokens", 10)
    huge = "z" * 1000
    msgs = [_user("old"), _user(huge)]
    out = await compact_history(msgs)
    # the last (huge) request must remain, otherwise there's nothing to send the model
    assert any(huge in _first_text(m) for m in out)


def test_agents_have_history_capability():
    from src.orchestrator.agents import assistant, coder, recon

    def has_compact(agent) -> bool:
        rc = agent.root_capability
        caps = getattr(rc, "capabilities", [rc])
        return any(getattr(c, "processor", None) is compact_history for c in caps)

    for mod in (assistant, recon, coder):
        assert has_compact(mod.agent), f"{mod.NAME} has no ProcessHistory"

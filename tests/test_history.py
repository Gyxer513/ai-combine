"""Тесты ужимания истории диалога (agents/history.py)."""

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
    msgs = [_user("привет"), _assistant("здравствуй")]
    out = await compact_history(list(msgs))
    assert out == msgs


async def test_empty_unchanged():
    assert await compact_history([]) == []


async def test_over_budget_trims_to_tail(monkeypatch):
    monkeypatch.setattr(settings, "history_max_tokens", 50)
    # каждое сообщение ~ (200//4 + 4) = 54 токена -> в бюджет влезает только хвост
    big = "x" * 200
    msgs = [_user(big), _assistant(big), _user(big), _assistant(big), _user("свежий вопрос")]
    out = await compact_history(msgs)
    assert len(out) < len(msgs)
    # последний пользовательский запрос сохранён (маркер вложен в то же сообщение)
    assert any("свежий вопрос" in _first_text(m) for m in out if isinstance(m, ModelRequest))
    # в начале — пометка об усечении
    assert _TRIM_MARKER in _first_text(out[0])


async def test_window_does_not_start_with_tool_return(monkeypatch):
    monkeypatch.setattr(settings, "history_max_tokens", 30)
    big = "y" * 200
    # tool-цикл: assistant вызывает инструмент -> request с tool-return -> финал
    msgs = [
        _user(big),
        ModelResponse(parts=[ToolCallPart(tool_name="t", args="{}", tool_call_id="1")]),
        ModelRequest(parts=[ToolReturnPart(tool_name="t", content=big, tool_call_id="1")]),
        _user("итоговый вопрос"),
    ]
    out = await compact_history(msgs)
    # первое сообщение окна — чистый user-request (с маркером), без tool-return
    assert isinstance(out[0], ModelRequest)
    assert any(isinstance(p, UserPromptPart) for p in out[0].parts)
    # осиротевший tool-return (без своего tool-call) выброшен из окна целиком
    assert not any(isinstance(p, ToolReturnPart) for m in out for p in m.parts)


async def test_keeps_last_message_even_if_huge(monkeypatch):
    monkeypatch.setattr(settings, "history_max_tokens", 10)
    huge = "z" * 1000
    msgs = [_user("старое"), _user(huge)]
    out = await compact_history(msgs)
    # последний (огромный) запрос обязан остаться, иначе нечего слать модели
    assert any(huge in _first_text(m) for m in out)


def test_agents_have_history_capability():
    from src.orchestrator.agents import assistant, coder, recon

    def has_compact(agent) -> bool:
        rc = agent.root_capability
        caps = getattr(rc, "capabilities", [rc])
        return any(getattr(c, "processor", None) is compact_history for c in caps)

    for mod in (assistant, recon, coder):
        assert has_compact(mod.agent), f"{mod.NAME} без ProcessHistory"

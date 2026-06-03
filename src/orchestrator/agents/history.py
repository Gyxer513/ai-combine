"""Ужимание истории диалога перед запросом к модели.

`compact_history` — процессор для Pydantic AI `ProcessHistory`: вызывается перед
КАЖДЫМ запросом к модели на обоих путях (Telegram `/chat` и OpenWebUI `/v1`), и
держит историю в пределах токен-бюджета. Системный промпт (`instructions=`)
передаётся отдельно и здесь не трогается.

Стратегия — детерминированное окно по бюджету (без LLM-вызова):
* считаем приблизительные токены, и если влезаем — отдаём как есть;
* иначе оставляем хвост (самые свежие сообщения) в пределах бюджета;
* стартовую границу окна сдвигаем до «чистого» пользовательского запроса, чтобы
  не оставить осиротевший tool-return без своего tool-call (иначе провайдер ругнётся);
* если что-то отрезали — в начало добавляем честную пометку об усечении.

LLM-суммаризация старого хвоста сознательно НЕ делается: на stateless-пути
OpenWebUI она пересчитывалась бы каждый ход (история приходит от клиента целиком) —
лишние деньги без кэша. Вернёмся к ней с персистом состояния по conversation_id.
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
    "[Системе: ранняя часть этого диалога свёрнута для экономии контекста. "
    "Если нужны детали из начала разговора — попроси пользователя напомнить.]"
)

# Грубая оценка: ~4 символа на токен + накладные на разметку сообщения.
_CHARS_PER_TOKEN = 4
_MSG_OVERHEAD_TOKENS = 4


def _content_text(content: object) -> str:
    """Достать текст из content части (строка или список мультимодальных кусков)."""
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence):
        return " ".join(c for c in content if isinstance(c, str))
    return str(content)


def _part_text(part: object) -> str:
    """Текстовое представление одной части сообщения для оценки размера."""
    content = getattr(part, "content", None)
    if content is not None:
        return _content_text(content)
    args = getattr(part, "args", None)  # ToolCallPart
    if args is not None:
        return args if isinstance(args, str) else str(args)
    return str(part)


def _message_tokens(msg: ModelMessage) -> int:
    """Приблизительные токены одного сообщения."""
    chars = sum(len(_part_text(p)) for p in msg.parts)
    return chars // _CHARS_PER_TOKEN + _MSG_OVERHEAD_TOKENS


def _is_clean_user_request(msg: ModelMessage) -> bool:
    """ModelRequest с пользовательским вводом и БЕЗ tool-return.

    Такое сообщение безопасно делать первым в окне: оно не ссылается на
    предыдущий (возможно отрезанный) tool-call.
    """
    if not isinstance(msg, ModelRequest):
        return False
    has_user = any(isinstance(p, (UserPromptPart, SystemPromptPart)) for p in msg.parts)
    has_tool_return = any(isinstance(p, ToolReturnPart) for p in msg.parts)
    return has_user and not has_tool_return


def _with_marker(first: ModelMessage) -> list[ModelMessage]:
    """Вернуть стартовое(ые) сообщение(я) окна с добавленной пометкой об усечении.

    Если первое сообщение — ModelRequest, вкладываем пометку в него же (не плодим
    лишний turn). Иначе кладём пометку отдельным запросом перед ним.
    """
    marker = UserPromptPart(content=_TRIM_MARKER)
    if isinstance(first, ModelRequest):
        return [ModelRequest(parts=[marker, *first.parts])]
    return [ModelRequest(parts=[marker]), first]


async def compact_history(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Ужать историю до токен-бюджета (см. модульный docstring)."""
    if not messages:
        return messages

    budget = settings.history_max_tokens
    if sum(_message_tokens(m) for m in messages) <= budget:
        return messages

    # Собираем хвост в пределах бюджета (хотя бы последнее сообщение — всегда).
    kept: list[ModelMessage] = []
    used = 0
    for msg in reversed(messages):
        tokens = _message_tokens(msg)
        if kept and used + tokens > budget:
            break
        kept.append(msg)
        used += tokens
    kept.reverse()

    # Сдвигаем начало окна до «чистого» пользовательского запроса.
    while len(kept) > 1 and not _is_clean_user_request(kept[0]):
        kept.pop(0)

    if len(kept) == len(messages):  # по факту ничего не отрезали
        return messages

    return [*_with_marker(kept[0]), *kept[1:]]

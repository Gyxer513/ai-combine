"""Тесты SQLite-персистентности: данные переживают «рестарт» (новый стор на файле)."""

from __future__ import annotations

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from src.orchestrator.metrics import Metrics
from src.orchestrator.persistence import Database
from src.orchestrator.tools.memory import ConversationStore


def _msgs(text: str):
    return [
        ModelRequest(parts=[UserPromptPart(content=text)]),
        ModelResponse(parts=[TextPart(content="ok")]),
    ]


def test_history_survives_new_store(tmp_path):
    db_file = str(tmp_path / "t.db")

    store1 = ConversationStore(Database(db_file))
    store1.extend_history("c1", _msgs("привет"))

    # «рестарт»: новый Database + стор на том же файле
    store2 = ConversationStore(Database(db_file))
    hist = store2.history("c1")
    assert len(hist) == 2
    assert hist[0].parts[0].content == "привет"


def test_notes_survive_new_store(tmp_path):
    db_file = str(tmp_path / "n.db")
    ConversationStore(Database(db_file)).save_note("c1", "city", "Владивосток")
    assert ConversationStore(Database(db_file)).get_note("c1", "city") == "Владивосток"


def test_clear_removes_history_and_notes(tmp_path):
    db = Database(str(tmp_path / "c.db"))
    store = ConversationStore(db)
    store.extend_history("c1", _msgs("x"))
    store.save_note("c1", "k", "v")
    store.clear("c1")
    assert store.history("c1") == []
    assert store.get_note("c1", "k") is None


def test_history_trim_persists(tmp_path):
    db = Database(str(tmp_path / "trim.db"))
    store = ConversationStore(db, max_messages=2)
    msgs = [ModelResponse(parts=[TextPart(content=str(i))]) for i in range(5)]
    store.extend_history("c1", msgs)
    assert len(store.history("c1")) == 2


def test_metrics_survive_new_instance(tmp_path):
    db_file = str(tmp_path / "m.db")
    m1 = Metrics(Database(db_file))
    m1.record("koschei", 100, 50)
    m1.record("koschei", 10, 5)

    m2 = Metrics(Database(db_file))  # «рестарт»
    a = m2.for_agent("koschei")
    assert a.requests == 2
    assert a.input_tokens == 110
    assert a.output_tokens == 55


def test_stats_counts_conversations_and_messages(tmp_path):
    store = ConversationStore(Database(str(tmp_path / "s.db")))
    store.extend_history("c1", _msgs("a"))  # 2 сообщения
    store.extend_history("c2", _msgs("b"))  # 2 сообщения
    convs, messages = store.stats()
    assert convs == 2
    assert messages == 4

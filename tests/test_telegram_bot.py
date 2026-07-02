import sqlite3
import sys
from pathlib import Path

import pytest

from genus import reactors
from genus.db import init_schema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy"))
import telegram_bot  # noqa: E402  (deploy/ script, imported directly for its pure logic)
import deuter  # noqa: E402


@pytest.fixture(autouse=True)
def _no_real_deuter_model(monkeypatch):
    """Every test here must behave the same regardless of whether a Deuter model happens to be
    installed on the machine running them (the deployed Pi has one; a fresh dev/CI box doesn't)
    -- force "not installed" by default, so a session-based test can't silently start loading
    the real 1.5B model just because a chat_id's message falls through to the fallback sentinel.
    Tests that specifically exercise the wiring monkeypatch ``deuter.interpret`` itself, which
    overrides this."""
    monkeypatch.setattr(deuter, "MODEL_PATH", "/nonexistent/path/model.gguf")


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _msg(update_id, sender_id, text, chat_id=None):
    return {
        "update_id": update_id,
        "message": {"from": {"id": sender_id}, "chat": {"id": chat_id or sender_id}, "text": text},
    }


def test_unauthorized_sender_is_ignored():
    conn = _fresh()
    result = telegram_bot.handle_update(conn, _msg(1, 999, "Was ist ein Hund?"), allowed={42})
    assert result is None


def test_authorized_sender_gets_answered_via_companion_respond():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    result = telegram_bot.handle_update(conn, _msg(1, 42, "Was ist ein Hund?"), allowed={42})
    assert result is not None
    chat_id, answer = result
    assert chat_id == 42 and "Wolf" in answer


def test_update_without_text_is_ignored():
    conn = _fresh()
    update = {"update_id": 1, "message": {"from": {"id": 42}, "chat": {"id": 42}}}  # no "text" (e.g. a photo)
    assert telegram_bot.handle_update(conn, update, allowed={42}) is None


def test_update_without_message_is_ignored():
    conn = _fresh()
    assert telegram_bot.handle_update(conn, {"update_id": 1}, allowed={42}) is None


def test_a_bug_in_answering_is_caught_not_raised(monkeypatch):
    conn = _fresh()
    from genus import companion
    monkeypatch.setattr(companion, "respond", lambda c, q: (_ for _ in ()).throw(RuntimeError("boom")))
    chat_id, answer = telegram_bot.handle_update(conn, _msg(1, 42, "irgendwas"), allowed={42})
    assert chat_id == 42 and "schiefgelaufen" in answer   # graceful, never crashes the loop


def test_sessions_let_a_bare_followup_retrace_the_previous_answer():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Haustier@de", "expresses", "Q_pet", "wikidata")
    reactors.observe_relation(conn, "Q144", "is_a", "Q_pet", "wikidata")
    sessions: dict = {}

    telegram_bot.handle_update(conn, _msg(1, 42, "Ist ein Hund ein Haustier?"), allowed={42}, sessions=sessions)
    chat_id, answer = telegram_bot.handle_update(conn, _msg(2, 42, "warum?"), allowed={42}, sessions=sessions)

    assert chat_id == 42
    assert "Herleitung" in answer and "wikidata" in answer   # retraced, not "kein Wort bekannt"


def test_sessions_are_kept_separate_per_chat():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    sessions: dict = {}

    telegram_bot.handle_update(conn, _msg(1, 42, "Was ist ein Hund?"), allowed={42}, sessions=sessions)
    # a DIFFERENT chat asks a bare followup with no history of its own -- must not see chat 42's question
    _, answer = telegram_bot.handle_update(
        conn, _msg(2, 42, "warum?", chat_id=99), allowed={42}, sessions=sessions,
    )
    assert "Herleitung" not in answer   # chat 99 has no prior turn -> ordinary routing, not a stale trace


def test_without_sessions_behaves_exactly_as_before():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    result = telegram_bot.handle_update(conn, _msg(1, 42, "Was ist ein Hund?"), allowed={42})   # no sessions
    assert result is not None and "Wolf" in result[1]


def test_bot_is_wired_to_the_deuter_as_a_last_resort(monkeypatch):
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    monkeypatch.setattr(deuter, "interpret", lambda q: {"intent": "definition", "subject": "Hund"})

    chat_id, answer = telegram_bot.handle_update(
        conn, _msg(1, 42, "so ne frage zu dem wuffwuff thema"), allowed={42}, sessions={},
    )
    assert chat_id == 42
    assert "Wolf" in answer and "Sprachmodell gedeutet" in answer


def test_bot_stays_honest_when_the_deuter_is_not_installed():
    # the autouse fixture above already forces "not installed" for every test in this file
    conn = _fresh()
    chat_id, answer = telegram_bot.handle_update(
        conn, _msg(1, 42, "voellig unverstaendliche anfrage"), allowed={42}, sessions={},
    )
    assert chat_id == 42
    assert "schiefgelaufen" not in answer   # no crash, just the ordinary honest fallback


def test_deuter_never_calls_a_real_question_a_statement():
    # live-caught 2026-07-02: "was ist ein Hund" (an unambiguous question) came back from the
    # real model as {"intent": "statement", ...} -- a structural, deterministic veto, not a
    # prompt tweak: ANY "statement" verdict for text that looks like a question is retried as
    # "definition" instead, regardless of what the model said.
    assert deuter._looks_like_question("was ist ein Hund")
    assert deuter._looks_like_question("Ist das so?")
    assert deuter._looks_like_question("kannst du mir das erklären")
    assert not deuter._looks_like_question("ich habe zwei Hunde")
    assert not deuter._looks_like_question("mein Geburtstag ist im Mai")


def test_allowed_ids_parses_comma_separated_list(monkeypatch):
    monkeypatch.setenv("GENUS_TELEGRAM_ALLOWED_IDS", "111, 222 ,333")
    assert telegram_bot._allowed_ids() == {111, 222, 333}


def test_allowed_ids_skips_malformed_entries(monkeypatch):
    monkeypatch.setenv("GENUS_TELEGRAM_ALLOWED_IDS", "111,notanumber,222")
    assert telegram_bot._allowed_ids() == {111, 222}


def test_allowed_ids_empty_by_default(monkeypatch):
    monkeypatch.delenv("GENUS_TELEGRAM_ALLOWED_IDS", raising=False)
    assert telegram_bot._allowed_ids() == set()


def test_main_refuses_to_start_without_a_token(monkeypatch, tmp_path):
    monkeypatch.delenv("GENUS_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(telegram_bot, "TOKEN_FILE", str(tmp_path / "no_such_token_file"))
    assert telegram_bot.main() == 1


def test_main_refuses_to_start_with_an_empty_allowlist(monkeypatch):
    monkeypatch.setenv("GENUS_TELEGRAM_BOT_TOKEN", "fake-token-for-test")
    monkeypatch.delenv("GENUS_TELEGRAM_ALLOWED_IDS", raising=False)
    assert telegram_bot.main() == 1

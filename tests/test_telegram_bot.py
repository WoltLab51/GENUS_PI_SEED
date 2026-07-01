import sqlite3
import sys
from pathlib import Path

import pytest

from genus import reactors
from genus.db import init_schema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy"))
import telegram_bot  # noqa: E402  (deploy/ script, imported directly for its pure logic)


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

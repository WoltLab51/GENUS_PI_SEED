import os
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
import stimme  # noqa: E402


class _FakeModel:
    """A minimal stand-in for llama_cpp.Llama's chat-completion surface -- no real model,
    no GGUF file, just the one method deuter.py/stimme.py actually call."""

    def __init__(self, reply: str):
        self.reply = reply
        self.calls: list = []

    def create_chat_completion(self, messages, max_tokens=None, temperature=None):
        self.calls.append(messages)
        return {"choices": [{"message": {"content": self.reply}}]}


@pytest.fixture(autouse=True)
def _no_real_deuter_model(monkeypatch):
    """Every test here must behave the same regardless of whether a Deuter model happens to be
    installed on the machine running them (the deployed Pi has one; a fresh dev/CI box doesn't)
    -- force "not installed" by default, so a session-based test can't silently start loading
    the real 1.5B model just because a chat_id's message falls through to the fallback sentinel.
    Tests that specifically exercise the wiring monkeypatch ``deuter.interpret``/``get_model``
    (and ``stimme.formuliere``), which override this."""
    monkeypatch.setattr(deuter, "MODEL_PATH", "/nonexistent/path/model.gguf")
    monkeypatch.setattr(stimme, "MODEL_PATH", "/nonexistent/path/model.gguf")


@pytest.fixture(autouse=True)
def _korrektur_datei_im_tmp(monkeypatch, tmp_path):
    """Die Lernkreis-Edge-Datei darf in Tests NIE ins echte ~/.genus schreiben."""
    monkeypatch.setattr(telegram_bot, "KORREKTUR_DATEI",
                        str(tmp_path / "korrekturen.jsonl"))


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


def test_session_threads_last_answer_into_the_meta_zellen(monkeypatch):
    # Antwort-Würfel Scheibe 1: a follow-up like "kürzer" needs the PREVIOUS answer, not just
    # the previous question -- the session must carry both across turns
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    lesarten = {"Was ist ein Hund?": {"absicht": "definition", "subject": "Hund"},
                "nochmal bitte": {"absicht": "wiederholen"}}
    monkeypatch.setattr(deuter, "interpret",
                        lambda q, absichten=None, grammatik=None, korrekturen=None: lesarten[q])
    sessions: dict = {}

    telegram_bot.handle_update(conn, _msg(1, 42, "Was ist ein Hund?"), allowed={42}, sessions=sessions)
    chat_id, answer = telegram_bot.handle_update(conn, _msg(2, 42, "nochmal bitte"), allowed={42}, sessions=sessions)

    assert chat_id == 42
    assert answer.startswith("Nochmal: ") and "Wolf" in answer


def test_authorized_owner_is_ignored_outside_the_private_chat():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    sessions: dict = {}

    telegram_bot.handle_update(conn, _msg(1, 42, "Was ist ein Hund?"), allowed={42}, sessions=sessions)
    # Persönliche Erinnerungen besitzen noch keinen Nutzer-/Raum-Namespace. Bis zur Föderation
    # antwortet der persönliche Kern deshalb ausschließlich im Owner-Direktchat, nie in Gruppen.
    result = telegram_bot.handle_update(
        conn, _msg(2, 42, "warum?", chat_id=99), allowed={42}, sessions=sessions,
    )
    assert result is None
    assert 99 not in sessions


def test_sessions_resolve_a_von_vorhin_backreference_across_two_turns():
    # Mehr-Zug-Arbeitsgedächtnis: Runde 3 fragt "von vorhin" -- muss Runde 1 (Fahrrad) treffen,
    # nicht die dazwischenliegende Runde 2 (ein Gruss ohne bekanntes Wort)
    conn = _fresh()
    reactors.observe_relation(conn, "Fahrrad@de", "expresses", "Q_fahrrad", "wikidata")
    reactors.observe_relation(conn, "Fahrrad@de", "primary_gloss", "ein Zweirad zum Fahren", "dbnary")
    sessions: dict = {}

    telegram_bot.handle_update(conn, _msg(1, 42, "Was ist ein Fahrrad?"), allowed={42}, sessions=sessions)
    telegram_bot.handle_update(conn, _msg(2, 42, "Hallo!"), allowed={42}, sessions=sessions)
    chat_id, answer = telegram_bot.handle_update(
        conn, _msg(3, 42, "was war das von vorhin?"), allowed={42}, sessions=sessions)

    assert chat_id == 42
    assert "Zweirad" in answer and "Was ist ein Fahrrad?" in answer


def test_session_turn_history_is_capped_not_unbounded():
    conn = _fresh()
    reactors.observe_relation(conn, "Fahrrad@de", "expresses", "Q_fahrrad", "wikidata")
    reactors.observe_relation(conn, "Fahrrad@de", "primary_gloss", "ein Zweirad zum Fahren", "dbnary")
    sessions: dict = {}
    for i in range(telegram_bot._VERLAUF_MAX + 4):
        telegram_bot.handle_update(conn, _msg(i, 42, f"Runde {i}"), allowed={42}, sessions=sessions)
    assert len(sessions[42]) == telegram_bot._VERLAUF_MAX


def test_pending_session_turn_waits_for_a_transport_neutral_response_id():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier", "dbnary")
    sessions: dict = {}
    pending: dict = {}

    result = telegram_bot.handle_update(
        conn, _msg(1, 42, "Was ist ein Hund?"), allowed={42}, sessions=sessions,
        pending=pending,
    )

    assert result is not None and sessions == {}
    assert pending["chat_id"] == 42
    assert pending["zug"]["question"] == "Was ist ein Hund?"
    assert "response_id" not in pending["zug"]
    assert telegram_bot._finalisiere_pending_zug(sessions, pending, response_id=117) is True
    assert pending == {}
    assert sessions[42][-1]["response_id"] == 117
    assert sessions[42][-1]["answer"] == result[1]


def test_delivered_answer_gets_a_privacy_sparse_outcome_and_the_new_renderer():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier", "dbnary")
    sessions: dict = {}
    pending: dict = {}

    _, answer = telegram_bot.handle_update(
        conn, _msg(1, 42, "Was ist ein Hund?"), allowed={42}, sessions=sessions,
        pending=pending,
    )

    assert answer.startswith("»Hund« bedeutet hier: Haustier.")
    assert sessions == {}
    assert conn.execute("SELECT COUNT(*) FROM response_outcome_log").fetchone()[0] == 0

    response_id = telegram_bot._bestaetige_zustellung(
        conn, sessions, pending, message_id=77,
    )

    assert isinstance(response_id, int) and response_id != 77
    assert sessions[42][-1]["response_id"] == response_id
    row = conn.execute(
        "SELECT * FROM response_outcome_log WHERE response_id = ?", (response_id,),
    ).fetchone()
    assert dict(row) == {
        "response_id": response_id,
        "channel": "telegram",
        "outcome": "answered",
        "readings": '["definition"]',
        "answer_mode": "core",
        "feedback_eligible": 1,
        "created_at": row["created_at"],
    }
    event_payload = conn.execute(
        "SELECT payload FROM event_log WHERE id = ?", (response_id,),
    ).fetchone()[0]
    assert set(__import__("json").loads(event_payload)) == {
        "channel", "outcome", "readings", "answer_mode", "feedback_eligible",
    }
    assert all(token not in event_payload for token in ("Hund", "Haustier", "42", "77"))


def test_missing_transport_receipt_creates_neither_outcome_nor_session_turn():
    conn = _fresh()
    sessions: dict = {}
    pending: dict = {}
    telegram_bot.handle_update(
        conn, _msg(1, 42, "Hallo!"), allowed={42}, sessions=sessions, pending=pending,
    )

    assert telegram_bot._bestaetige_zustellung(
        conn, sessions, pending, message_id=None,
    ) is None
    assert pending == {} and sessions == {}
    assert conn.execute("SELECT COUNT(*) FROM response_outcome_log").fetchone()[0] == 0


def test_explicit_thumb_feedback_links_to_last_eligible_delivered_answer():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier", "dbnary")
    sessions: dict = {}
    pending: dict = {}

    telegram_bot.handle_update(
        conn, _msg(1, 42, "Was ist ein Hund?"), allowed={42}, sessions=sessions,
        pending=pending,
    )
    ziel_id = telegram_bot._bestaetige_zustellung(conn, sessions, pending, message_id=71)

    _, ack = telegram_bot.handle_update(
        conn, _msg(2, 42, "👍"), allowed={42}, sessions=sessions, pending=pending,
    )
    assert ack and pending["outcome"]["answer_mode"] == "feedback_ack"
    assert pending["outcome"]["feedback_eligible"] is False
    feedback = conn.execute(
        "SELECT response_id, signal, corrected_intent, source FROM response_feedback_log"
    ).fetchone()
    assert tuple(feedback) == (ziel_id, "positive", None, "owner_explicit")

    ack_id = telegram_bot._bestaetige_zustellung(conn, sessions, pending, message_id=72)
    assert sessions[42][-1]["response_id"] == ack_id
    assert sessions[42][-1]["feedback_eligible"] is False

    # Ein weiteres Signal darf nicht auf den Bestätigungs-Ack kippen: der ist explizit
    # ausgeschlossen; Ziel bleibt die letzte echte Antwort.
    telegram_bot.handle_update(
        conn, _msg(3, 42, "👍"), allowed={42}, sessions=sessions, pending=pending,
    )
    links = conn.execute(
        "SELECT response_id, signal FROM response_feedback_log ORDER BY feedback_event_id"
    ).fetchall()
    assert [tuple(row) for row in links] == [(ziel_id, "positive"), (ziel_id, "positive")]


@pytest.mark.parametrize("regung", ["❤️", "😊", "🔥", "🎉", "💪"])
def test_social_emoji_is_not_misread_as_answer_quality_feedback(regung):
    assert telegram_bot._explizites_feedback(regung) is None


def test_feedback_stops_at_a_delivered_edge_ritual_barrier():
    conn = _fresh()
    sessions: dict = {}
    pending: dict = {}
    telegram_bot.handle_update(
        conn, _msg(1, 42, "Hallo!"), allowed={42}, sessions=sessions, pending=pending,
    )
    telegram_bot._bestaetige_zustellung(conn, sessions, pending, message_id=73)
    telegram_bot.handle_update(
        conn, _msg(2, 42, "stell den Push auf 6:45"), allowed={42}, sessions=sessions,
        pending=pending,
    )
    telegram_bot._bestaetige_zustellung(conn, sessions, pending, message_id=74)
    assert sessions[42][-1]["answer_mode"] == "edge_ritual"

    telegram_bot.handle_update(
        conn, _msg(3, 42, "👍"), allowed={42}, sessions=sessions, pending=pending,
    )

    assert conn.execute("SELECT COUNT(*) FROM response_feedback_log").fetchone()[0] == 0


def test_textual_model_lob_is_not_promoted_to_explicit_feedback(monkeypatch):
    conn = _fresh()
    sessions: dict = {}
    pending: dict = {}
    telegram_bot.handle_update(
        conn, _msg(1, 42, "Hallo!"), allowed={42}, sessions=sessions, pending=pending,
    )
    telegram_bot._bestaetige_zustellung(conn, sessions, pending, message_id=81)
    monkeypatch.setattr(
        deuter, "interpret",
        lambda *a, **k: {"absicht": "lob", "subject": None, "object": None},
    )

    telegram_bot.handle_update(
        conn, _msg(2, 42, "Das war wirklich erfreulich formuliert"), allowed={42},
        sessions=sessions, pending=pending,
    )

    assert conn.execute("SELECT COUNT(*) FROM response_feedback_log").fetchone()[0] == 0
    assert pending["outcome"]["answer_mode"] == "core"
    assert pending["outcome"]["feedback_eligible"] is True


def test_explicit_intent_correction_links_structurally_without_chat_text():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier", "dbnary")
    sessions: dict = {}
    pending: dict = {}
    telegram_bot.handle_update(
        conn, _msg(1, 42, "Was ist ein Hund?"), allowed={42}, sessions=sessions,
        pending=pending,
    )
    ziel_id = telegram_bot._bestaetige_zustellung(conn, sessions, pending, message_id=91)

    telegram_bot.handle_update(
        conn, _msg(2, 42, "falsch verstanden: definition"), allowed={42},
        sessions=sessions, pending=pending,
    )

    feedback = conn.execute(
        "SELECT response_id, signal, corrected_intent, source FROM response_feedback_log"
    ).fetchone()
    assert tuple(feedback) == (ziel_id, "intent_correction", "definition", "owner_explicit")
    payload = conn.execute(
        "SELECT payload FROM event_log WHERE event_type = 'response_feedback_recorded'"
    ).fetchone()[0]
    assert "Hund" not in payload and "falsch verstanden" not in payload
    assert pending["outcome"]["answer_mode"] == "feedback_ack"


def test_unknown_correction_token_never_crosses_the_ledger_privacy_boundary():
    conn = _fresh()
    sessions: dict = {}
    pending: dict = {}
    telegram_bot.handle_update(
        conn, _msg(1, 42, "Hallo!"), allowed={42}, sessions=sessions, pending=pending,
    )
    ziel_id = telegram_bot._bestaetige_zustellung(conn, sessions, pending, message_id=92)

    telegram_bot.handle_update(
        conn, _msg(2, 42, "falsch verstanden: ronnygeheim"), allowed={42},
        sessions=sessions, pending=pending,
    )

    row = conn.execute(
        "SELECT response_id, corrected_intent FROM response_feedback_log"
    ).fetchone()
    assert tuple(row) == (ziel_id, None)
    payload = conn.execute(
        "SELECT payload FROM event_log WHERE event_type = 'response_feedback_recorded'"
    ).fetchone()[0]
    assert "ronnygeheim" not in payload


def test_answer_exception_is_a_delivered_non_feedbackable_error_outcome(monkeypatch):
    conn = _fresh()
    sessions: dict = {}
    pending: dict = {}
    from genus import companion

    monkeypatch.setattr(
        companion, "respond_with_deuter",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    _, answer = telegram_bot.handle_update(
        conn, _msg(1, 42, "Irgendetwas"), allowed={42}, sessions=sessions,
        pending=pending,
    )
    assert "schiefgelaufen" in answer

    response_id = telegram_bot._bestaetige_zustellung(
        conn, sessions, pending, message_id=101,
    )
    row = conn.execute(
        "SELECT outcome, answer_mode, feedback_eligible FROM response_outcome_log "
        "WHERE response_id = ?", (response_id,),
    ).fetchone()
    assert tuple(row) == ("fallback", "error", 0)
    assert sessions[42][-1]["answer_mode"] == "error"
    assert sessions[42][-1]["feedback_eligible"] is False


def test_session_contains_exactly_the_text_telegram_can_deliver(monkeypatch):
    conn = _fresh()
    sessions: dict = {}
    pending: dict = {}
    from genus import companion

    monkeypatch.setattr(
        companion, "respond_with_deuter",
        lambda *a, **k: {
            "text": "x" * (telegram_bot._TELEGRAM_TEXT_MAX + 500),
            "question": "lang",
            "gelesen": ["definition"],
            "outcome": "answered",
        },
    )
    _, answer = telegram_bot.handle_update(
        conn, _msg(1, 42, "lang"), allowed={42}, sessions=sessions, pending=pending,
    )

    assert len(answer) == telegram_bot._TELEGRAM_TEXT_MAX
    assert pending["zug"]["answer"] == answer


@pytest.mark.parametrize("response_id", [None, 0, -1, True, "117"])
def test_pending_session_turn_is_discarded_without_a_valid_response_id(response_id):
    conn = _fresh()
    sessions: dict = {}
    pending: dict = {}
    telegram_bot.handle_update(
        conn, _msg(1, 42, "Hallo!"), allowed={42}, sessions=sessions, pending=pending,
    )

    assert pending
    assert telegram_bot._finalisiere_pending_zug(sessions, pending, response_id) is False
    assert pending == {} and sessions == {}


def test_pending_session_turn_cannot_reuse_an_existing_response_id():
    sessions = {42: [{"question": "alt", "answer": "alt", "response_id": 7}]}
    pending = {"chat_id": 42, "zug": {"question": "neu", "answer": "neu"}}

    assert telegram_bot._finalisiere_pending_zug(sessions, pending, response_id=7) is False
    assert pending == {}
    assert [z["question"] for z in sessions[42]] == ["alt"]


def test_an_ignored_update_clears_a_stale_pending_turn_fail_closed():
    conn = _fresh()
    pending = {"chat_id": 42, "zug": {"question": "alt", "answer": "alt"}}

    assert telegram_bot.handle_update(
        conn, _msg(2, 999, "Hallo!"), allowed={42}, sessions={}, pending=pending,
    ) is None
    assert pending == {}


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
    monkeypatch.setattr(deuter, "interpret",
                        lambda q, absichten=None, grammatik=None, korrekturen=None: {"absicht": "definition",
                                                                   "subject": "Hund"})

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


def test_deuter_never_calls_a_plain_worker_statement_a_provenance_question():
    text = "Ich teste dich grad, denn wir haben einen neuen Worker angeschlossen"
    wrong = {
        "text": text,
        "absicht": "warum-herkunft",
        "subject": "GENUS",
        "object": None,
    }
    assert deuter._segment(wrong, text) == {
        "text": text,
        "absicht": "tatsache",
        "subject": "GENUS",
        "object": None,
    }


def test_core_rejects_provenance_without_a_provenance_signal_even_after_a_genus_greeting():
    from genus import antwort, companion

    conn = _fresh()
    result = companion.respond_with_deuter(
        conn,
        "Ich teste dich grad, denn wir haben einen neuen Worker angeschlossen",
        last_question="Hallo GENUS",
        last_answer="Hallo! Schön, dass du da bist.",
        deuter=lambda question: {
            "text": question,
            "absicht": "warum-herkunft",
            "subject": "GENUS",
            "object": None,
        },
        renderer=antwort.rendere,
    )
    assert result["outcome"] == "fallback"
    assert result["gelesen"] == []
    assert "Herkunft" not in result["text"]
    assert "Q162378" not in result["text"]


def test_deuter_interpret_distinguishes_explicit_empty_from_hard_failure(monkeypatch):
    # live gefunden: "OK prima" bekam wortwörtlich "[]" vom echten Modell zurück -- eine
    # erfolgreich geparste, aber LEERE Liste ist ein anderes Signal als "Modell/JSON kaputt"
    monkeypatch.setattr(deuter, "MODEL_PATH", __file__)   # eine echt existierende Datei genügt
    monkeypatch.setattr(deuter, "_get_model", lambda: _FakeModel("[]"))
    assert deuter.interpret("OK prima") == []

    monkeypatch.setattr(deuter, "_get_model", lambda: _FakeModel("das ist kein JSON"))
    assert deuter.interpret("kaputte antwort") is None


def test_deuter_reserves_only_a_compact_structured_output_window(monkeypatch):
    class CapturingModel(_FakeModel):
        def create_chat_completion(self, messages, max_tokens=None, temperature=None):
            self.max_tokens = max_tokens
            return super().create_chat_completion(messages, max_tokens, temperature)

    fake = CapturingModel("[]")
    monkeypatch.setattr(deuter, "MODEL_PATH", __file__)
    monkeypatch.setattr(deuter, "_get_model", lambda: fake)
    assert deuter.interpret("Hallo") == []
    assert fake.max_tokens == deuter.MAX_OUTPUT_TOKENS == 160


def test_deuter_deduplicates_identical_model_segments():
    item = {"text": "Tschüss", "absicht": "abschied", "subject": None, "object": None}
    assert deuter.clean_segments([item, dict(item)], "Tschüss") == [item]


def test_deuter_compact_mode_releases_only_after_idle_timeout(monkeypatch):
    class Closable:
        def __init__(self):
            self.closed = 0

        def close(self):
            self.closed += 1

    model = Closable()
    monkeypatch.setenv("GENUS_DEUTER_IDLE_SECONDS", "90")
    monkeypatch.setattr(deuter, "_model", model)
    monkeypatch.setattr(deuter, "_model_last_used_at", 100.0)

    assert deuter.release_if_idle(now=189.9) is False
    assert deuter.release_if_idle(now=190.0) is True
    assert model.closed == 1
    assert deuter._model is None


def test_deuter_compact_mode_zero_keeps_model_warm(monkeypatch):
    monkeypatch.setenv("GENUS_DEUTER_IDLE_SECONDS", "0")
    monkeypatch.setattr(deuter, "_model", object())
    monkeypatch.setattr(deuter, "_model_last_used_at", 1.0)
    assert deuter.release_if_idle(now=9999.0) is False


def test_telegram_waage_is_an_explicit_compact_mode_opt_in(monkeypatch):
    monkeypatch.delenv("GENUS_TELEGRAM_WAAGE", raising=False)
    assert telegram_bot._waage_aktiv() is False
    monkeypatch.setenv("GENUS_TELEGRAM_WAAGE", "1")
    assert telegram_bot._waage_aktiv() is True


def test_stimme_anchors_extracts_every_quoted_word_and_number():
    satz = "Unter »Hund« versteht GENUS: Haustier. (Vertrauen 0.50 — hergeleitet.)"
    assert stimme._anchors(satz) == ["Hund", "0.50"]


def test_stimme_formuliere_returns_the_rephrase_when_every_anchor_survives():
    # seit dem Hausvögel-Fund (2026-07-04) gilt die doppelte Leine: Anker (zitierte
    # Wörter, Zahlen) UND jedes tragende Substantiv müssen überleben -- eine Umformung,
    # die "Vorfahre" zu "abstammt" macht, wäre legitim, wird aber bewusst geopfert
    # (abgelehnter guter Stil kostet nichts, durchgelassene Korruption kostet Wahrheit)
    satz = "Unter »Hund« versteht GENUS: Haustier, dessen Vorfahre der Wolf ist."
    model = _FakeModel("Ein »Hund« ist ein Haustier — sein Vorfahre ist der Wolf.")
    result = stimme.formuliere(satz, model=model)
    assert result == model.reply
    assert model.calls and model.calls[0][1]["content"] == satz   # the original, unmodified


def test_deuter_merkmale_liest_die_fakten_in_beweisarten():
    # Fakt→Merkmal: das Modell liefert {merkmal: evidenz}; das Modul reicht nur saubere
    # String→String-Paare durch (der Kern, genus.recht.subsumiere_frei, prüft gegen die Norm)
    blaetter = [{"id": "merkmal:angebot", "inhalt": "ein Angebot"},
                {"id": "merkmal:faelligkeit", "inhalt": "fällig"}]
    model = _FakeModel('{"merkmal:angebot": "erfuellt_urkunde", "merkmal:faelligkeit": "erfuellt_aussage"}')
    deuter._model = model
    try:
        deuter.MODEL_PATH = __file__   # os.path.exists True -> _get_model() wird gerufen
        gelesen = deuter.merkmale("ich habe verkauft ...", blaetter)
    finally:
        deuter._model = None
    assert gelesen == {"merkmal:angebot": "erfuellt_urkunde", "merkmal:faelligkeit": "erfuellt_aussage"}
    # der Merkmale-Prompt trägt die Voraussetzungen (der Kern liefert sie über die Membran)
    assert "merkmal:angebot" in model.calls[0][0]["content"]


def test_stimme_formuliere_fails_safe_when_an_anchor_goes_missing():
    # the model dropped the quoted word entirely -- a faithfulness violation, not a style choice
    satz = "Unter »Hund« versteht GENUS: Haustier."
    model = _FakeModel("Ein Tier, das gerne bellt.")
    assert stimme.formuliere(satz, model=model) is None


def test_stimme_catches_a_corrupted_category_name_when_it_is_a_quoted_anchor():
    # live fund (2026-07-03): companion.narrate() left is_a-category names UNQUOTED, so a
    # rephrase could silently corrupt one ("Kernobst" -> "Kernaubere") without the anchor
    # check ever noticing -- only the headword was protected. Fixed at the source (companion
    # now quotes every named category), which this pins from the Stimme's side: once quoted,
    # a corrupted category name is exactly the kind of anchor loss formuliere() must catch.
    satz = "Unter »Apfel« versteht GENUS: Frucht; es zählt zu »Kernobst« und »Obst«."
    model = _FakeModel("»Apfel« ist laut GENUS eine Frucht aus der Familie der Kernaubere.")
    assert stimme.formuliere(satz, model=model) is None


def test_stimme_formuliere_fails_safe_when_a_number_is_altered():
    satz = "Ja. »Apfel« zählt zu »Pflanzen«. (Vertrauen 0.50 — hergeleitet.)"
    model = _FakeModel("»Apfel« gehört laut GENUS zu »Pflanzen«. (Vertrauen 0.95 — hergeleitet.)")
    assert stimme.formuliere(satz, model=model) is None   # the model must not invent confidence


def test_stimme_formuliere_fails_safe_when_provider_appends_new_claims():
    satz = "Ja — »Hund« zählt zu »Haustier«."
    model = _FakeModel(
        "Ja, »Hund« zählt zu »Haustier«. Hunde werden oft als Wachhunde oder Begleiter gehalten."
    )
    assert stimme.formuliere(satz, model=model) is None


def test_stimme_formuliere_returns_none_without_a_model_and_none_installed():
    # the autouse fixture forces stimme.MODEL_PATH to a nonexistent path
    assert stimme.formuliere("Unter »Hund« versteht GENUS: Haustier.") is None


def test_bot_can_opt_in_to_the_separate_stimme_model(monkeypatch):
    # Die zweite Modellkopie ist seit dem 4-GiB-Live-Befund kein Default mehr. Wer die optionale
    # Glättung ausdrücklich einschaltet, bekommt weiterhin die getrennte Stimme (kein Teilen:
    # das verdrängte den Deuter-Prompt-Cache und machte den nächsten Aufruf 26s langsam).
    monkeypatch.setenv("GENUS_TELEGRAM_STIMME", "1")
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    assert not hasattr(deuter, "get_model")
    seen_models = []

    def spy(satz, model=None):
        seen_models.append(model)
        return "»Hund« ist laut GENUS ein Haustier, das vom Wolf abstammt."
    monkeypatch.setattr(stimme, "formuliere", spy)

    chat_id, answer = telegram_bot.handle_update(
        conn, _msg(1, 42, "Was ist ein Hund?"), allowed={42}, sessions={},
    )
    assert seen_models == [None]   # kein geteiltes Modell durchgereicht -- stimme lädt ihr eigenes
    assert "Sprachlich vom Modell geglättet" in answer


def test_bot_does_not_load_stimme_by_default_and_keeps_the_complete_answer(monkeypatch):
    monkeypatch.delenv("GENUS_TELEGRAM_STIMME", raising=False)
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    monkeypatch.setattr(
        deuter, "interpret",
        lambda q, absichten=None, grammatik=None, korrekturen=None:
            {"absicht": "definition", "subject": "Hund"},
    )

    def unerlaubt(*args, **kwargs):
        raise AssertionError("Stimme must stay unloaded without an explicit opt-in")

    monkeypatch.setattr(stimme, "formuliere", unerlaubt)
    chat_id, answer = telegram_bot.handle_update(
        conn, _msg(1, 42, "Was ist ein Hund?"), allowed={42}, sessions={},
    )
    assert chat_id == 42 and "Wolf" in answer
    assert "Sprachlich vom Modell geglättet" not in answer


def test_bot_falls_back_to_the_template_when_no_model_is_installed():
    # the autouse fixture forces "not installed" -- stimme must never be consulted, and the
    # plain deterministic answer must reach the user unmarked
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    chat_id, answer = telegram_bot.handle_update(
        conn, _msg(1, 42, "Was ist ein Hund?"), allowed={42}, sessions={},
    )
    assert "Wolf" in answer and "geglättet" not in answer


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


def test_main_refuses_multiple_owners_until_memories_are_isolated(monkeypatch):
    monkeypatch.setenv("GENUS_TELEGRAM_BOT_TOKEN", "fake-token-for-test")
    monkeypatch.setattr(telegram_bot, "_allowed_ids", lambda: {41, 42})

    assert telegram_bot.main() == 1


def test_instance_lock_rejects_a_second_poller(monkeypatch, tmp_path):
    # Portable fake for Linux flock (the test suite also runs on Windows): the second open
    # simulates a competing process. The bot must request EX|NB and close/reject that instance.
    import types

    calls = []

    def flock(fd, flags):
        calls.append((fd, flags))
        if len(calls) == 2:
            raise BlockingIOError("already locked")

    fake_fcntl = types.SimpleNamespace(LOCK_EX=1, LOCK_NB=2, flock=flock)
    monkeypatch.setitem(sys.modules, "fcntl", fake_fcntl)
    monkeypatch.setattr(telegram_bot, "INSTANCE_LOCK_FILE", str(tmp_path / "telegram.lock"))

    first = telegram_bot._acquire_instance_lock()
    try:
        assert first is not None
        assert telegram_bot._acquire_instance_lock() is None
        assert [flags for _, flags in calls] == [3, 3]
    finally:
        first.close()


def test_main_stops_before_db_and_network_when_poll_lock_is_owned(monkeypatch, tmp_path):
    from genus import db

    monkeypatch.setattr(telegram_bot, "_token", lambda: "test-token")
    monkeypatch.setattr(telegram_bot, "_allowed_ids", lambda: {42})
    monkeypatch.setattr(telegram_bot, "LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(telegram_bot, "_acquire_instance_lock", lambda: None)
    monkeypatch.setattr(
        db, "connect", lambda path: (_ for _ in ()).throw(AssertionError("must not open DB")),
    )
    assert telegram_bot.main() == 0


def test_main_treats_telegram_409_as_a_competing_poller_and_stops(monkeypatch, tmp_path):
    from genus import db

    monkeypatch.setattr(telegram_bot, "_token", lambda: "test-token")
    monkeypatch.setattr(telegram_bot, "_allowed_ids", lambda: {42})
    monkeypatch.setattr(telegram_bot, "LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(telegram_bot, "_acquire_instance_lock", lambda: object())
    monkeypatch.setattr(db, "connect", lambda path: object())
    monkeypatch.setattr(telegram_bot, "_load_offset", lambda: 0)

    def konflikt(token, offset):
        raise telegram_bot.urllib.error.HTTPError(
            "https://api.telegram.invalid", 409, "Conflict", None, None,
        )

    monkeypatch.setattr(telegram_bot, "_get_updates", konflikt)
    assert telegram_bot.main() == 0


def test_bot_verbindet_ueber_genus_db_connect_nicht_roh():
    # Phase 0 der Ziel-Architektur: der Bot bekommt dieselben Pragmas (WAL, busy_timeout)
    # und Spalten-Migrationen wie die CLI. Ein roher sqlite3.connect in main() hiess:
    # dieser eine Zugang konnte sich auf einer frischen/unmigrierten DB anders verhalten
    # als jeder andere. Struktur-Gate wie test_membrane_purity: der Quelltext selbst
    # wird geprueft, damit die Abweichung nicht zurueckschleichen kann.
    quelle = (ROOT / "deploy" / "telegram_bot.py").read_text(encoding="utf-8")
    assert "db.connect(" in quelle
    assert "sqlite3.connect(" not in quelle


# --- Phase 2 der Ziel-Architektur: die GRENZE (constrained decoding) + Naht 5 ---------


def test_deuter_spiegel_driftet_nie_vom_raster(conn):
    # Naht 5: der hartkodierte Spiegel (DEFAULT_ABSICHTEN/_GRUPPEN/_ERKLAERUNGEN) konnte
    # vom gesaeten Raster wegdriften -- LIVE SO PASSIERT: "berechnen" war gesaet, aber im
    # Spiegel unbekannt und wurde vom gruppierten Prompt still verschluckt. Dieser Pin
    # bricht CI an der Stelle, wo die Drift entsteht (eine Code-Aenderung an nur einer
    # der beiden Seiten).
    from genus import verstehen

    raster_blaetter = {leaf for leaf, _ in verstehen.RASTER_SEED}
    assert set(deuter.DEFAULT_ABSICHTEN) == raster_blaetter | {"unklar"}
    # jedes Blatt hat eine Erklaerung und einen Platz in genau einer Prompt-Gruppe
    gruppiert = [b for _, blaetter in deuter._GRUPPEN for b in blaetter]
    assert sorted(gruppiert) == sorted(set(gruppiert)), "ein Blatt in zwei Gruppen"
    assert set(gruppiert) == raster_blaetter
    assert set(deuter._ERKLAERUNGEN) == raster_blaetter | {"unklar"}


def test_system_prompt_verschluckt_kein_angebotenes_blatt_mehr():
    # Das Auffangnetz: ein im Graphen gesaetes Blatt ohne Gruppen-Zuordnung im Spiegel
    # erscheint trotzdem im Prompt (unter WEITERE) statt still zu verschwinden.
    prompt = deuter._system_prompt(("definition", "voellig-neues-blatt"))
    assert "voellig-neues-blatt" in prompt
    assert "WEITERE" in prompt


def test_gbnf_grammatik_kompiliert_die_blaetter_als_grenze():
    from genus import verstehen

    grammatik = verstehen.gbnf_grammatik(("definition", "dank"))
    assert grammatik.startswith("root ::=")
    # jedes Blatt ist eine einkompilierte Alternative, unklar immer dabei
    assert '"\\"definition\\""' in grammatik
    assert '"\\"dank\\""' in grammatik
    assert '"\\"unklar\\""' in grammatik
    # der Segment-Vertrag (die vier Schluessel in fester Reihenfolge) steht drin
    for schluessel in ("text", "absicht", "subject", "object"):
        assert f'\\"{schluessel}\\"' in grammatik
    # genau drei Klauseln reichen fuer "Hallo + Frage + Danke"; keine Endlos-Wiederholung
    assert grammatik.splitlines()[0].count("segment") == 3
    assert "segment)*" not in grammatik
    assert "ws ::= [ \\t\\n\\r]*" not in grammatik
    # ohne Angebot: das RASTER_SEED ist die Grenze
    voll = verstehen.gbnf_grammatik(None)
    assert '"\\"berechnen\\""' in voll


class _FakeModelMitKwargs(_FakeModel):
    def __init__(self, reply: str):
        super().__init__(reply)
        self.kwargs: list[dict] = []

    def create_chat_completion(self, messages, max_tokens=None, temperature=None, **kwargs):
        self.kwargs.append(kwargs)
        return super().create_chat_completion(messages, max_tokens, temperature)


def test_interpret_reicht_die_grenze_ans_modell_durch(monkeypatch):
    fake = _FakeModelMitKwargs('[{"text": "hi", "absicht": "gruss", "subject": null, '
                               '"object": null}]')
    monkeypatch.setattr(deuter, "MODEL_PATH", __file__)
    monkeypatch.setattr(deuter, "_get_model", lambda: fake)
    monkeypatch.setattr(deuter, "_gbnf", lambda text: f"KOMPILIERT:{len(text)}")

    ergebnis = deuter.interpret("hi", grammatik="root ::= irgendwas")
    assert ergebnis and ergebnis[0]["absicht"] == "gruss"
    assert fake.kwargs == [{"grammar": f"KOMPILIERT:{len('root ::= irgendwas')}"}]


def test_unbrauchbare_grammatik_degradiert_ehrlich_statt_zu_schweigen(monkeypatch, capsys):
    # _gbnf kann nicht kompilieren -> lauter stderr-Hinweis, aber der Deuter laeuft
    # UNBESCHRAENKT weiter (der Bot bleibt antwortfaehig; der Verlust der Garantie
    # passiert nie still). ZWEI Pi-Deploy-Funde stecken in diesem Test: (1) "root ::=
    # kaputt" war auf dem Pi GUELTIGES GBNF (llama_cpp installiert; der Test lief nur
    # auf der Dev-Box gruen); (2) der Pi-Parser schluckt sogar eine offene Klammer --
    # auf Parser-Strenge laesst sich nicht wetten. Also wird das Scheitern hermetisch
    # INJIZIERT: ein Fake-llama_cpp, dessen from_string wirft -- deterministisch auf
    # jeder Maschine, und es testet exakt unseren except-Pfad. (Der echte Fehlerfall
    # auf dem Pi laege ohnehin erst beim Generieren -- den faengt interprets
    # try/except -> None -> ehrlicher Wort-Lookup-Fallback.)
    import types

    kaputtes_llama = types.ModuleType("llama_cpp")

    class _KaputteGrammatik:
        @staticmethod
        def from_string(text, verbose=False):
            raise ValueError("injiziert: kompiliert nie")

    kaputtes_llama.LlamaGrammar = _KaputteGrammatik
    monkeypatch.setitem(sys.modules, "llama_cpp", kaputtes_llama)

    fake = _FakeModelMitKwargs('[{"text": "hi", "absicht": "gruss", "subject": null, '
                               '"object": null}]')
    monkeypatch.setattr(deuter, "MODEL_PATH", __file__)
    monkeypatch.setattr(deuter, "_get_model", lambda: fake)
    deuter._grammatik_cache.clear()

    ergebnis = deuter.interpret("hi", grammatik="root ::= irrelevant")
    assert ergebnis and ergebnis[0]["absicht"] == "gruss"
    assert fake.kwargs == [{}]   # keine Grammatik durchgereicht
    assert "UNBESCHRÄNKT" in capsys.readouterr().err
    deuter._grammatik_cache.clear()


def test_bot_leitet_die_grenze_aus_dem_lebenden_raster_ab(monkeypatch):
    conn = _fresh()
    from genus import verstehen
    verstehen.seed_raster(conn)
    empfangen: dict = {}

    def fake_interpret(q, absichten=None, grammatik=None, korrekturen=None):
        empfangen["absichten"] = absichten
        empfangen["grammatik"] = grammatik
        return [{"text": q, "absicht": "gruss", "subject": None, "object": None}]

    monkeypatch.setattr(deuter, "interpret", fake_interpret)
    telegram_bot.handle_update(conn, _msg(1, 42, "Hallo!"), allowed={42}, sessions={})

    assert empfangen["grammatik"] is not None and empfangen["grammatik"].startswith("root ::=")
    # die Grenze kommt aus demselben lebenden Angebot wie der Prompt
    assert '"\\"berechnen\\""' in empfangen["grammatik"]


def test_fabrizierter_segment_text_wird_nicht_geglaubt(monkeypatch):
    # Live-Fund (Pi, 2026-07-04): das Modell meldete ein Segment mit dem Text
    # "f'(x) = 2x + 3" -- selbst ausgerechnet, steht nirgends in der Nachricht. Die
    # Grammatik erzwingt Struktur, nicht Herkunft; die prueft der deterministische
    # Segment-Filter: fabrizierter Text -> das ganze Segment samt erfundener Absicht faellt weg.
    fake = _FakeModelMitKwargs(
        '[{"text": "f\'(x) = 2x + 3", "absicht": "berechnen", "subject": null, '
        '"object": null}]'
    )
    monkeypatch.setattr(deuter, "MODEL_PATH", __file__)
    monkeypatch.setattr(deuter, "_get_model", lambda: fake)

    nachricht = "Bestimme die Ableitung von f(x) = x^2 + 3x"
    ergebnis = deuter.interpret(nachricht)
    assert ergebnis == []

    # ein ECHTER Teil-Text der Nachricht bleibt dagegen unangetastet
    fake2 = _FakeModelMitKwargs(
        '[{"text": "Danke!", "absicht": "dank", "subject": null, "object": null}]'
    )
    monkeypatch.setattr(deuter, "_get_model", lambda: fake2)
    ergebnis2 = deuter.interpret("Was ist ein Hund? Danke!")
    assert ergebnis2 and ergebnis2[0]["text"] == "Danke!"


# --- Phase 3 Scheibe 3: der enge Korrektur-Kanal (Naht 1) -----------------------------


def test_korrektur_cue_ist_exakt_und_deutungsfrei():
    from genus import companion

    assert companion.korrektur_cue("falsch verstanden") == (True, None)
    assert companion.korrektur_cue("Falsch gedeutet!") == (True, None)
    assert companion.korrektur_cue("falsch verstanden: beziehung") == (True, "beziehung")
    # ein laengerer Satz ist KEIN Cue -- er muesste sonst durch genau den Klassifikator,
    # der eben danebengriff (zirkulaer, Naht 1)
    assert companion.korrektur_cue("das hast du falsch verstanden, glaube ich") == (False, None)
    assert companion.korrektur_cue("Was ist ein Hund?") == (False, None)


def test_korrektur_haelt_fehlgriff_als_struktur_fest_nie_text():
    from genus import companion, verstehen

    conn = _fresh()
    verstehen.seed_raster(conn)
    result = companion.respond_with_deuter(
        conn, "falsch verstanden", last_question="Wie wird das Wetter morgen?",
        letzte_lesarten=["abschied"],
    )
    assert "abschied" in result["text"] and "gemerkt" in result["text"]
    assert result["question"] == "Wie wird das Wetter morgen?"   # Anker bleibt beim Thema
    assert verstehen.fehlgriffe(conn, "abschied")["gesamt"] == 1
    # Ledger≠Memory: der Wortlaut der korrigierten Frage steht NIRGENDS im Ledger
    rows = conn.execute("SELECT payload FROM event_log").fetchall()
    assert all("Wetter morgen" not in r["payload"] for r in rows)


def test_korrektur_mit_blattnamen_haelt_die_verwechslung_fest():
    from genus import companion, sources, verstehen

    conn = _fresh()
    verstehen.seed_raster(conn)
    result = companion.respond_with_deuter(
        conn, "falsch verstanden: weltfrage", letzte_lesarten=["abschied"],
    )
    assert "weltfrage" in result["text"]
    kanten = sources.relations(conn, subject="absicht:abschied",
                               predicate=verstehen.FEHLGRIFF_STATT)
    assert [k["object"] for k in kanten] == ["absicht:weltfrage"]


def test_korrektur_mit_unbekanntem_blatt_bleibt_ehrlich():
    from genus import companion, verstehen

    conn = _fresh()
    verstehen.seed_raster(conn)
    result = companion.respond_with_deuter(
        conn, "falsch verstanden: quatschblatt", letzte_lesarten=["dank"],
    )
    assert "kenne ich allerdings nicht" in result["text"]
    assert verstehen.fehlgriffe(conn, "dank")["gesamt"] == 1   # der Fehlgriff zaehlt trotzdem


def test_korrektur_ohne_letzte_deutung_antwortet_ehrlich_und_schreibt_nichts():
    from genus import companion

    conn = _fresh()
    vorher = conn.execute("SELECT COUNT(*) AS n FROM event_log").fetchone()["n"]
    result = companion.respond_with_deuter(conn, "falsch verstanden")
    assert "keine letzte Deutung" in result["text"]
    nachher = conn.execute("SELECT COUNT(*) AS n FROM event_log").fetchone()["n"]
    assert nachher == vorher


def test_bot_faedelt_gelesen_durch_die_session_ende_zu_ende(monkeypatch):
    # Zug 1: der Deuter greift daneben (liest eine Wetterfrage als "abschied").
    # Zug 2: das exakte "falsch verstanden" korrigiert -- Ende zu Ende ueber die Session.
    from genus import verstehen

    conn = _fresh()
    verstehen.seed_raster(conn)
    monkeypatch.setattr(deuter, "interpret",
                        lambda q, absichten=None, grammatik=None, korrekturen=None:
                        [{"text": q, "absicht": "abschied", "subject": None, "object": None}])
    sessions: dict = {}

    telegram_bot.handle_update(conn, _msg(1, 42, "Wie wird das Wetter morgen?"),
                               allowed={42}, sessions=sessions)
    assert sessions[42][-1]["gelesen"] == ["abschied"]
    chat_id, answer = telegram_bot.handle_update(conn, _msg(2, 42, "falsch verstanden"),
                                                 allowed={42}, sessions=sessions)
    assert chat_id == 42 and "abschied" in answer
    assert verstehen.fehlgriffe(conn, "abschied")["gesamt"] == 1
    # der Korrektur-Zug selbst traegt keine Lesart -- eine Doppel-Korrektur laeuft nie im Kreis
    assert sessions[42][-1]["gelesen"] == []


# --- Lernkreis v1 (Naht 4): Verwechslungs-Wissen + Korrektur-Beispiele ----------------


def test_verwechslungen_trennen_muster_von_einzelfall():
    from genus import verstehen

    conn = _fresh()
    verstehen.seed_raster(conn)
    # zweimal dieselbe Verwechslung = Muster; einmal eine andere = Einzelfall
    verstehen.record_fehlgriff(conn, "abschied", "weltfrage")
    verstehen.record_fehlgriff(conn, "abschied", "weltfrage")
    verstehen.record_fehlgriff(conn, "gruss", "dank")
    v = verstehen.verwechslungen(conn)
    assert v == [{"gelesen": "abschied", "gemeint": "weltfrage", "n": 2}]
    # eine einzelne Korrektur allein bleibt unter der Gueltigkeits-Saat
    conn2 = _fresh()
    verstehen.record_fehlgriff(conn2, "gruss", "dank")
    assert verstehen.verwechslungen(conn2) == []


def test_deuter_prompt_traegt_den_lernkreis_rueckfluss():
    prompt = deuter._system_prompt(None, [
        {"gelesen": "abschied", "gemeint": "weltfrage"},
        {"gelesen": "abschied", "gemeint": "weltfrage",
         "beispiel": "Wie wird das Wetter morgen?"},
    ])
    assert "BEKANNTE FEHLGRIFFE" in prompt
    assert 'lies im Zweifel "weltfrage" statt "abschied"' in prompt
    assert "Wie wird das Wetter morgen? -> weltfrage" in prompt
    # ohne Korrekturen: kein Abschnitt (der Prompt-Praefix bleibt exakt wie vorher)
    assert "BEKANNTE FEHLGRIFFE" not in deuter._system_prompt(None)


def test_merke_korrektur_datei_bleibt_gedeckelt():
    import json as _json

    for i in range(telegram_bot._KORREKTUR_MAX + 7):
        telegram_bot._merke_korrektur(f"Frage {i}", ["abschied"], "weltfrage")
    zeilen = open(telegram_bot.KORREKTUR_DATEI, encoding="utf-8").read().splitlines()
    assert len(zeilen) == telegram_bot._KORREKTUR_MAX
    assert _json.loads(zeilen[-1])["text"] == f"Frage {telegram_bot._KORREKTUR_MAX + 6}"


def test_korrektur_zug_landet_als_beispiel_in_der_edge_datei(monkeypatch):
    import json as _json
    from genus import verstehen

    conn = _fresh()
    verstehen.seed_raster(conn)
    monkeypatch.setattr(deuter, "interpret",
                        lambda q, absichten=None, grammatik=None, korrekturen=None:
                        [{"text": q, "absicht": "abschied", "subject": None, "object": None}])
    sessions: dict = {}
    telegram_bot.handle_update(conn, _msg(1, 42, "Wie wird das Wetter morgen?"),
                               allowed={42}, sessions=sessions)
    telegram_bot.handle_update(conn, _msg(2, 42, "falsch verstanden: weltfrage"),
                               allowed={42}, sessions=sessions)
    zeilen = open(telegram_bot.KORREKTUR_DATEI, encoding="utf-8").read().splitlines()
    eintrag = _json.loads(zeilen[-1])
    assert eintrag == {"text": "Wie wird das Wetter morgen?",
                       "falsch": ["abschied"], "richtig": "weltfrage"}


def test_naechste_nachricht_bekommt_den_rueckfluss_in_den_deuter(monkeypatch):
    from genus import verstehen

    conn = _fresh()
    verstehen.seed_raster(conn)
    # gelebte Historie: zweimal korrigierte Verwechslung im Graphen + ein Beispiel in der Datei
    verstehen.record_fehlgriff(conn, "abschied", "weltfrage")
    verstehen.record_fehlgriff(conn, "abschied", "weltfrage")
    telegram_bot._merke_korrektur("Wie wird das Wetter morgen?", ["abschied"], "weltfrage")
    empfangen: dict = {}

    def fake_interpret(q, absichten=None, grammatik=None, korrekturen=None):
        empfangen["korrekturen"] = korrekturen
        return [{"text": q, "absicht": "gruss", "subject": None, "object": None}]

    monkeypatch.setattr(deuter, "interpret", fake_interpret)
    telegram_bot.handle_update(conn, _msg(1, 42, "Hallo!"), allowed={42}, sessions={})

    k = empfangen["korrekturen"]
    assert {"gelesen": "abschied", "gemeint": "weltfrage"} in k
    assert any(e.get("beispiel") == "Wie wird das Wetter morgen?" for e in k)


# --- der Selbst-Neustart: kein sudo mehr für Deploys (Ronny, 2026-07-04) --------------


def test_neustart_flag_zaehlt_nur_wenn_frischer_als_der_prozess(monkeypatch, tmp_path):
    import os as _os
    import time as _time

    flag = tmp_path / "telegram_bot.neustart"
    monkeypatch.setattr(telegram_bot, "NEUSTART_DATEI", str(flag))
    jetzt = _time.time()
    # kein Flag -> kein Neustart
    assert telegram_bot._neustart_angefordert(jetzt) is False
    # ein ALTES Flag (Ueberbleibsel von vor dem Start) -> kein Neustart, keine Schleife
    flag.write_text("", encoding="utf-8")
    _os.utime(flag, (jetzt - 100, jetzt - 100))
    assert telegram_bot._neustart_angefordert(jetzt) is False
    # ein frisches Flag (Deploy NACH Prozess-Start) -> Neustart
    _os.utime(flag, (jetzt + 5, jetzt + 5))
    assert telegram_bot._neustart_angefordert(jetzt) is True


def test_deploy_beruehrt_das_neustart_flag():
    # Struktur-Gate: der Deploy fordert den Bot-Neustart automatisch an -- die Aera
    # "sudo systemctl restart" nach jedem Deploy ist vorbei.
    text = (ROOT / "deploy" / "pi_deploy.sh").read_text(encoding="utf-8")
    assert "telegram_bot.neustart" in text


def test_bot_installer_ist_sudo_fest_und_setzt_den_nutzer():
    # Live gefunden (2026-07-04): unter sudo ist $HOME /root -- der Installer suchte den
    # Token am falschen Ort UND haette den Dienst als root laufen lassen. Struktur-Gate:
    # SUDO_USER-Aufloesung wie in den anderen Pi-Skripten + User= in der Unit.
    text = (ROOT / "deploy" / "pi_install_telegram_bot.sh").read_text(encoding="utf-8")
    assert "SUDO_USER" in text
    assert "getent passwd" in text
    assert "User=$GENUS_USER" in text


# --- die erste HAND: Erinnerungen (P4) -------------------------------------------------

def test_erinnerung_parser_um_zeit_und_inhalt():
    import datetime as dt
    faellig, inhalt = telegram_bot._erinnerung("erinnere mich um 18 an den Anruf",
                                               dt.datetime(2026, 7, 8, 10, 0))
    assert faellig == dt.datetime(2026, 7, 8, 18, 0) and inhalt == "den Anruf"


def test_erinnerung_parser_in_delta():
    import datetime as dt
    faellig, inhalt = telegram_bot._erinnerung("erinner mich in 15 minuten an das Brot",
                                               dt.datetime(2026, 7, 8, 10, 0))
    assert faellig == dt.datetime(2026, 7, 8, 10, 15) and inhalt == "das Brot"


def test_erinnerung_parser_vergangene_uhrzeit_wird_morgen():
    import datetime as dt
    faellig, _ = telegram_bot._erinnerung("erinnere mich um 8:00 daran, dass ich Milch kaufe",
                                          dt.datetime(2026, 7, 8, 20, 0))
    assert faellig == dt.datetime(2026, 7, 9, 8, 0)   # 8 Uhr heute vorbei -> morgen


def test_erinnerung_parser_ohne_zeit_oder_kein_befehl_ist_keine():
    import datetime as dt
    jetzt = dt.datetime(2026, 7, 8, 10, 0)
    assert telegram_bot._erinnerung("erinnere mich an den Anruf", jetzt) is None   # keine Zeit
    assert telegram_bot._erinnerung("Was ist ein Hund?", jetzt) is None


def test_erinnerung_ritual_legt_eine_bestaetigte_hand_an():
    from genus import hand
    conn = _fresh()
    ergebnis = telegram_bot.handle_update(conn, _msg(1, 42, "erinnere mich um 23:59 an die Milch"),
                                          allowed={42})
    assert ergebnis is not None
    _, antwort = ergebnis
    assert "Mach ich" in antwort and "die Milch" in antwort
    offen = hand.offene(conn)
    assert len(offen) == 1
    assert offen[0]["status"] == hand.FREIGEGEBEN and "die Milch" in offen[0]["inhalt"]


def test_ein_absturz_im_erinnerungs_ritual_toetet_die_bruecke_nicht(monkeypatch):
    # Review-Fund (HIGH): das Erinnerungs-Ritual SCHREIBT ins Ledger, VOR dem Kern. Reisst dieser
    # Schreib ab (vorübergehender Lock), darf das die Brücke NICHT stürzen lassen -- sonst friert
    # der Offset ein (er wird erst NACH handle_update gespeichert) und Telegram stellt genau diese
    # Nachricht endlos neu zu = Neustart-Schleife. Wie ein Fehler im Antworten: graziös abfangen.
    conn = _fresh()
    from genus import hand
    monkeypatch.setattr(hand, "vorschlagen",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("database is locked")))
    chat_id, answer = telegram_bot.handle_update(conn, _msg(1, 42, "erinnere mich in 5 minuten an X"),
                                                 allowed={42})
    assert chat_id == 42 and "schiefgelaufen" in answer   # gefangen, nie geworfen -> Offset speichert


# --- der Tagespuffer: nur Struktur, kein Gesprächsmitschnitt ----------------------------


@pytest.fixture(autouse=True)
def _tagespuffer_im_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(telegram_bot, "TAGESPUFFER", str(tmp_path / "chat_tag.jsonl"))


def test_jeder_zug_wandert_in_den_tagespuffer():
    import json as _json

    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss",
                              "Haustier, Vorfahre der Wolf", "dbnary")
    telegram_bot.handle_update(conn, _msg(1, 42, "Was ist ein Hund?"),
                               allowed={42}, sessions={})
    zeilen = open(telegram_bot.TAGESPUFFER, encoding="utf-8").read().splitlines()
    assert len(zeilen) == 1
    zug = _json.loads(zeilen[0])
    assert zug["konzepte"] == ["Q144"]
    assert set(zug) == {"ts", "konzepte", "warum_folge", "gelesen"}
    assert "Was ist ein Hund?" not in zeilen[0] and "Wolf" not in zeilen[0]


def test_telegram_journal_bekommt_nur_metadaten_keinen_rohtext_oder_absender(monkeypatch):
    protokoll = []
    monkeypatch.setattr(telegram_bot, "_log", protokoll.append)
    conn = _fresh()

    telegram_bot.handle_update(conn, _msg(1, 42, "mein sehr privater Satz"),
                               allowed={42}, sessions={})

    text = "\n".join(protokoll)
    assert "characters=" in text
    assert "privater" not in text and "42" not in text


def test_morgen_push_und_nacht_stehen_im_cron_installer():
    text = (ROOT / "deploy" / "pi_install_cron.sh").read_text(encoding="utf-8")
    assert "nacht_konsolidierung.sh" in text
    assert "morgen_push.sh" in text


def test_der_besinnungs_herzschlag_ist_rein_reflektierend():
    # der autonome Herzschlag (Ronny 2026-07-05): tickt GENUS' Geist, schreibt NUR ins
    # Membran-Tagebuch -- kein --tick (kein Proposal), keine Außenwirkung, nichts ins Ledger
    text = (ROOT / "deploy" / "besinnung.sh").read_text(encoding="utf-8")
    assert "genus\" besinnung" in text or "genus besinnung" in text
    assert "--tick" not in text                       # rein lesend: nie ein Proposal
    assert "sendMessage" not in text and "curl" not in text   # keine Außenwirkung
    assert "besinnung.log" in text                    # schreibt ins Membran-Tagebuch
    cron = (ROOT / "deploy" / "pi_install_cron.sh").read_text(encoding="utf-8")
    assert "besinnung.sh" in cron                      # als Herzschlag im Cron verdrahtet


# --- Vokabel-bei-Begegnung: die Membran legt unbekannte Wörter in die Lern-Warteschlange ---


@pytest.fixture(autouse=True)
def _lernwunsch_im_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(telegram_bot, "LERNWUNSCH", str(tmp_path / "lernwunsch.jsonl"))


def _lernwunsch(bot):
    with open(bot.LERNWUNSCH, encoding="utf-8") as f:
        return [z.strip() for z in f if z.strip()]


def test_ein_unbekanntes_wort_landet_nur_nach_opt_in_in_der_lernwarteschlange(monkeypatch):
    monkeypatch.setenv("GENUS_CHAT_WORD_LEARNING", "1")
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "ein Haustier", "dbnary")
    telegram_bot.handle_update(conn, _msg(1, 42, "Hat ein Hund auch Fernweh?"),
                               allowed={42}, sessions={})
    assert _lernwunsch(telegram_bot) == ["Fernweh"]   # „Hund" ist bekannt, „Hat" gefiltert


def test_lernwarteschlange_dedupliziert_ueber_nachrichten(monkeypatch):
    monkeypatch.setenv("GENUS_CHAT_WORD_LEARNING", "1")
    conn = _fresh()
    for _ in range(3):
        telegram_bot.handle_update(conn, _msg(1, 42, "Was bedeutet Fernweh?"),
                                   allowed={42}, sessions={})
    assert _lernwunsch(telegram_bot) == ["Fernweh"]   # dreimal begegnet, einmal in der Schlange


def test_chat_wortlernen_ist_standardmaessig_aus():
    conn = _fresh()

    telegram_bot.handle_update(conn, _msg(1, 42, "Was bedeutet Privatname?"),
                               allowed={42}, sessions={})

    assert not os.path.exists(telegram_bot.LERNWUNSCH)


def test_schreibe_lernwunsch_bleibt_gedeckelt():
    telegram_bot._schreibe_lernwunsch([f"Wort{i}" for i in range(telegram_bot._LERNWUNSCH_MAX + 30)])
    assert len(_lernwunsch(telegram_bot)) == telegram_bot._LERNWUNSCH_MAX


def test_der_lerner_holt_die_begegnung_vor_den_listen():
    # struktureller Gate-Test: learn_begegnung läuft VOR learn_fach/next/gap (gesprächsnah)
    text = (ROOT / "deploy" / "pi_learn.sh").read_text(encoding="utf-8")
    assert "learn_begegnung || learn_fach || learn_next || learn_gap" in text
    assert "if learn_begegnung; then" in text   # auch in der kontinuierlichen Schleife
    assert 'GENUS_CHAT_WORD_LEARNING:-0' in text  # private Wörter verlassen den Pi nur opt-in
    assert 'content redacted' in text and "word '$word'" not in text
    assert 'flock -x "$lock_fd"' in text and 'chmod 600 "$tmp"' in text


# --- die Morgenzeit-Zelle: Push-Zeit per Chat stellen (Membran-Konfiguration) ----------


@pytest.fixture(autouse=True)
def _morgenzeit_datei_im_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(telegram_bot, "MORGENZEIT_DATEI", str(tmp_path / "morgenpush.zeit"))


def test_morgenzeit_stellen_schreibt_die_datei_die_der_push_liest():
    antwort = telegram_bot._morgenzeit_antwort("Stell den Push auf 7")
    assert "07:00" in antwort
    inhalt = open(telegram_bot.MORGENZEIT_DATEI, encoding="utf-8").read()
    assert inhalt == "07:00"   # exakt das Format, das morgen_push.sh string-vergleicht


def test_morgenzeit_versteht_minuten_und_uhr_suffix():
    antwort = telegram_bot._morgenzeit_antwort("stell den Morgen-Push auf 6:30 Uhr!")
    assert "06:30" in antwort
    assert open(telegram_bot.MORGENZEIT_DATEI, encoding="utf-8").read() == "06:30"


def test_morgenzeit_ausserhalb_des_fensters_wird_gestellt_aber_ehrlich_benannt():
    antwort = telegram_bot._morgenzeit_antwort("stell den Push auf 12")
    assert "12:00" in antwort and "Morgen-Fenster" in antwort


def test_morgenzeit_weist_eine_unmoegliche_uhrzeit_ab():
    antwort = telegram_bot._morgenzeit_antwort("stell den Push auf 25")
    assert "keine gültige Uhrzeit" in antwort
    import os as _os
    assert not _os.path.exists(telegram_bot.MORGENZEIT_DATEI)   # nichts geschrieben


def test_morgenzeit_frage_nennt_standard_und_gestellten_wert():
    assert "06:00" in telegram_bot._morgenzeit_antwort("Wann kommt der Push?")
    telegram_bot._morgenzeit_antwort("stell den Push auf 7:15")
    assert "07:15" in telegram_bot._morgenzeit_antwort("wann kommt die Morgen-Nachricht?")


def test_eine_gewoehnliche_frage_ist_kein_morgenzeit_kommando():
    assert telegram_bot._morgenzeit_antwort("Was ist ein Hund?") is None
    assert telegram_bot._morgenzeit_antwort("Wann kommt der Frühling?") is None


def test_morgenzeit_kommando_laeuft_als_membran_ritual_vor_dem_kern():
    # das Kommando erreicht weder Deuter noch Session-Buchführung -- reine Membran-Sache
    conn = _fresh()
    sessions: dict = {}
    result = telegram_bot.handle_update(conn, _msg(1, 42, "stell den Push auf 6:45"),
                                        allowed={42}, sessions=sessions)
    assert result is not None and "06:45" in result[1]
    assert sessions == {}   # kein Zug, kein Verlauf -- Konfiguration ist kein Gespräch


# --- die „GENUS denkt …"-Statuszeile (Ronny 2026-07-09: „machts irgendwie spannender") ----
# Status als INJIZIERTER Callback (dasselbe Muster wie deuter/stimme): ohne ihn bleibt
# handle_update pur (alle bestehenden Tests beweisen das mit); der Melder verwandelt die
# Status-Nachricht per editMessageText in die fertige Antwort.

def test_status_meldet_denken_vor_dem_deuter(monkeypatch):
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "ein Haustier", "dbnary")
    monkeypatch.setattr(
        deuter, "interpret",
        lambda q, absichten=None, grammatik=None, korrekturen=None:
            {"absicht": "definition", "subject": "Hund"})
    gemeldet: list = []
    telegram_bot.handle_update(conn, _msg(1, 42, "Was ist ein Hund?"), allowed={42},
                               sessions={}, status=lambda cid, t: gemeldet.append((cid, t)))
    assert gemeldet and gemeldet[0][0] == 42 and "denke" in gemeldet[0][1]


def test_antwortmelder_sendet_dann_editiert(monkeypatch):
    rufe: list = []

    def fake_api(token, method, params, timeout):
        rufe.append((method, dict(params)))
        return {"ok": True, "result": {"message_id": 77}}

    monkeypatch.setattr(telegram_bot, "_api", fake_api)
    m = telegram_bot._AntwortMelder("tok")
    m.melde(42, "🤔 Ich denke nach …")
    m.melde(42, "✍️ Ich formuliere …")
    message_id = m.abschliessen(42, "Die Antwort.")
    assert [r[0] for r in rufe] == ["sendMessage", "editMessageText", "editMessageText"]
    assert rufe[1][1]["message_id"] == 77 and rufe[2][1]["text"] == "Die Antwort."
    assert message_id == 77
    assert 42 not in m._nachricht   # abgeschlossen -> vergessen (kein Geister-Edit spaeter)


def test_antwortmelder_ohne_meldung_sendet_schlicht(monkeypatch):
    rufe: list = []
    monkeypatch.setattr(
        telegram_bot, "_api",
        lambda t, meth, p, timeout: (rufe.append(meth), {"ok": True, "result": {"message_id": 1}})[1])
    m = telegram_bot._AntwortMelder("tok")
    message_id = m.abschliessen(42, "Direkte Antwort.")   # schneller Pfad hatte nie einen Status
    assert rufe == ["sendMessage"]
    assert message_id == 1


def test_antwortmelder_returns_the_fallback_message_id_when_editing_fails(monkeypatch):
    rufe: list = []

    def fake_api(token, method, params, timeout):
        rufe.append(method)
        if method == "editMessageText":
            raise OSError("Editieren gescheitert")
        message_id = 9 if len(rufe) == 1 else 10
        return {"ok": True, "result": {"message_id": message_id}}

    monkeypatch.setattr(telegram_bot, "_api", fake_api)
    m = telegram_bot._AntwortMelder("tok")
    m.melde(42, "🤔 Ich denke nach …")

    assert m.abschliessen(42, "Die Antwort.") == 10
    assert rufe == ["sendMessage", "editMessageText", "sendMessage"]


def test_antwortmelder_rejects_a_malformed_edit_receipt_and_sends_fresh(monkeypatch):
    rufe: list = []

    def fake_api(token, method, params, timeout):
        rufe.append(method)
        if method == "editMessageText":
            return {"ok": True}  # kein Message-Objekt, also kein Beleg für den finalen Text
        message_id = 9 if len(rufe) == 1 else 10
        return {"ok": True, "result": {"message_id": message_id}}

    monkeypatch.setattr(telegram_bot, "_api", fake_api)
    m = telegram_bot._AntwortMelder("tok")
    m.melde(42, "🤔 Ich denke nach …")

    assert m.abschliessen(42, "Die Antwort.") == 10
    assert rufe == ["sendMessage", "editMessageText", "sendMessage"]


@pytest.mark.parametrize(
    "body",
    [
        {"ok": False},
        {"ok": True},
        {"ok": True, "result": {}},
        {"ok": True, "result": True},
        {"ok": True, "result": {"message_id": True}},
        {"ok": True, "result": {"message_id": "7"}},
        None,
    ],
)
def test_send_message_without_an_integer_receipt_returns_none(monkeypatch, body):
    monkeypatch.setattr(telegram_bot, "_api", lambda *a, **k: body)

    assert telegram_bot._send_message("tok", 42, "Antwort") is None


def test_antwortmelder_meldung_ist_fail_silent(monkeypatch):
    def kracht(*a, **k):
        raise OSError("Netz weg")
    monkeypatch.setattr(telegram_bot, "_api", kracht)
    m = telegram_bot._AntwortMelder("tok")
    m.melde(42, "🤔 …")   # darf NIE werfen -- Status ist Zucker, keine Pflicht
    assert 42 not in m._nachricht


def test_antwortmelder_raeumt_haengende_meldungen_auf(monkeypatch):
    rufe: list = []

    def fake_api(token, method, params, timeout):
        rufe.append(method)
        return {"ok": True, "result": {"message_id": 9}}

    monkeypatch.setattr(telegram_bot, "_api", fake_api)
    m = telegram_bot._AntwortMelder("tok")
    m.melde(42, "🤔 Ich denke nach …")
    m.raeume_auf("Da ist etwas schiefgelaufen.")   # nie ein ewiges „denke nach" stehen lassen
    assert rufe == ["sendMessage", "editMessageText"] and not m._nachricht

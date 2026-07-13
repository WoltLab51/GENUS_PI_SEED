import json
import sqlite3

import pytest

from genus import event_router, integrity, ledger, response_outcomes


def _outcome(conn, **overrides) -> int:
    values = {
        "channel": "telegram",
        "outcome": "answered",
        "readings": ["definition"],
        "answer_mode": "core",
        "feedback_eligible": True,
    }
    values.update(overrides)
    return response_outcomes.record_outcome(conn, **values)


def test_outcome_event_id_is_response_id_and_payload_is_privacy_exact(conn):
    response_id = _outcome(conn, readings=["definition", "anschlussfrage"])

    event = conn.execute(
        "SELECT id, payload, created_at FROM event_log WHERE id = ?", (response_id,)
    ).fetchone()
    payload = json.loads(event["payload"])
    assert event["id"] == response_id
    assert payload == {
        "answer_mode": "core",
        "channel": "telegram",
        "feedback_eligible": True,
        "outcome": "answered",
        "readings": ["definition", "anschlussfrage"],
    }
    assert set(payload) == response_outcomes.OUTCOME_PAYLOAD_KEYS
    assert not {
        "question",
        "answer",
        "text",
        "slots",
        "chat_id",
        "user_id",
        "message_id",
    } & set(payload)

    projected = conn.execute(
        "SELECT * FROM response_outcome_log WHERE response_id = ?", (response_id,)
    ).fetchone()
    assert projected["response_id"] == response_id
    assert json.loads(projected["readings"]) == ["definition", "anschlussfrage"]
    assert projected["feedback_eligible"] == 1
    assert projected["created_at"] == event["created_at"]


@pytest.mark.parametrize("outcome", sorted(response_outcomes.OUTCOMES))
def test_all_four_response_outcomes_are_persistable(conn, outcome):
    response_id = _outcome(conn, outcome=outcome)
    row = conn.execute(
        "SELECT outcome FROM response_outcome_log WHERE response_id = ?", (response_id,)
    ).fetchone()
    assert row["outcome"] == outcome


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"channel": "web"}, "channel"),
        ({"outcome": "maybe"}, "outcome"),
        ({"answer_mode": "freeform"}, "answer_mode"),
        ({"feedback_eligible": 1}, "boolean"),
        ({"readings": "definition"}, "must be a list"),
        ({"readings": ["definition", "definition"]}, "duplicates"),
        ({"readings": ["private sentence with spaces"]}, "structural intent token"),
        (
            {"answer_mode": "feedback_ack", "feedback_eligible": True},
            "must not be feedback eligible",
        ),
        (
            {"answer_mode": "error", "feedback_eligible": True},
            "must not be feedback eligible",
        ),
    ],
)
def test_outcome_producer_rejects_non_structural_values(conn, override, message):
    with pytest.raises(ValueError, match=message):
        _outcome(conn, **override)
    assert conn.execute("SELECT COUNT(*) FROM event_log").fetchone()[0] == 0


def test_feedback_links_an_eligible_response_without_conversation_content(conn):
    response_id = _outcome(conn, readings=["abschied"])
    feedback_id = response_outcomes.record_feedback(
        conn,
        response_id=response_id,
        signal="intent_correction",
        corrected_intent="weltfrage",
    )

    event = conn.execute(
        "SELECT payload, created_at FROM event_log WHERE id = ?", (feedback_id,)
    ).fetchone()
    payload = json.loads(event["payload"])
    assert payload == {
        "corrected_intent": "weltfrage",
        "response_id": response_id,
        "signal": "intent_correction",
        "source": "owner_explicit",
    }
    assert set(payload) == response_outcomes.FEEDBACK_PAYLOAD_KEYS

    projected = conn.execute(
        "SELECT * FROM response_feedback_log WHERE feedback_event_id = ?", (feedback_id,)
    ).fetchone()
    assert projected["response_id"] == response_id
    assert projected["signal"] == "intent_correction"
    assert projected["corrected_intent"] == "weltfrage"
    assert projected["source"] == "owner_explicit"
    assert projected["created_at"] == event["created_at"]


def test_intent_correction_may_leave_the_correct_intent_unknown(conn):
    response_id = _outcome(conn)
    feedback_id = response_outcomes.record_feedback(
        conn, response_id=response_id, signal="intent_correction"
    )
    row = conn.execute(
        "SELECT corrected_intent FROM response_feedback_log WHERE feedback_event_id = ?",
        (feedback_id,),
    ).fetchone()
    assert row["corrected_intent"] is None


def test_feedback_rejects_unknown_and_ineligible_response_ids(conn):
    with pytest.raises(ValueError, match="unknown response_id"):
        response_outcomes.record_feedback(conn, response_id=999, signal="negative")

    ack_id = _outcome(
        conn,
        answer_mode="feedback_ack",
        feedback_eligible=False,
        readings=[],
    )
    with pytest.raises(ValueError, match="not feedback eligible"):
        response_outcomes.record_feedback(conn, response_id=ack_id, signal="positive")

    assert conn.execute(
        "SELECT COUNT(*) FROM event_log WHERE event_type = ?",
        (response_outcomes.FEEDBACK_EVENT,),
    ).fetchone()[0] == 0


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"response_id": True, "signal": "positive"}, "positive integer"),
        ({"response_id": 1, "signal": "ambivalent"}, "signal"),
        (
            {
                "response_id": 1,
                "signal": "positive",
                "corrected_intent": "definition",
            },
            "only valid for intent_correction",
        ),
        ({"response_id": 1, "signal": "negative", "source": "model"}, "source"),
    ],
)
def test_feedback_payload_enums_are_closed(conn, kwargs, message):
    with pytest.raises(ValueError, match=message):
        response_outcomes.record_feedback(conn, **kwargs)


def test_response_projections_are_replay_stable_and_integrity_checked(conn):
    first = _outcome(conn, readings=["definition"])
    response_outcomes.record_feedback(conn, response_id=first, signal="positive")
    _outcome(
        conn,
        outcome="fallback",
        readings=[],
        answer_mode="core",
        feedback_eligible=True,
    )
    before = integrity.snapshot_projections(conn)

    summary = event_router.replay(conn)
    after = integrity.snapshot_projections(conn)

    assert after == before
    assert summary["response_outcomes"] == 2
    assert summary["response_feedback"] == 1
    checked = integrity.check(conn)
    assert checked["ok"] is True
    assert checked["response_outcomes"] == 2
    assert checked["response_feedback"] == 1


def test_integrity_rejects_extra_private_outcome_fields(conn):
    ledger.append(
        conn,
        response_outcomes.OUTCOME_EVENT,
        {
            "channel": "telegram",
            "outcome": "answered",
            "readings": ["definition"],
            "answer_mode": "core",
            "feedback_eligible": True,
            "answer": "this must never enter the ledger",
        },
    )
    issues = integrity.validate_event_contract(conn)
    assert any("privacy contract forbids extra keys: answer" in issue for issue in issues)


def test_integrity_rejects_feedback_without_an_earlier_eligible_outcome(conn):
    ledger.append(
        conn,
        response_outcomes.FEEDBACK_EVENT,
        {
            "response_id": 2,
            "signal": "negative",
            "corrected_intent": None,
            "source": "owner_explicit",
        },
    )
    _outcome(conn, readings=[])

    issues = integrity.validate_event_contract(conn)
    assert any("does not reference an earlier valid response outcome" in issue for issue in issues)


def test_integrity_check_reports_invalid_feedback_link_without_replay_crash(conn):
    ledger.append(
        conn,
        response_outcomes.FEEDBACK_EVENT,
        {
            "response_id": 999,
            "signal": "negative",
            "corrected_intent": None,
            "source": "owner_explicit",
        },
    )

    result = integrity.check(conn)

    assert result["ok"] is False
    assert any("does not reference an earlier valid response outcome" in issue
               for issue in result["issues"])
    assert not any("projection replay failed" in issue for issue in result["issues"])


@pytest.mark.parametrize("payload", ["[]", "null", "1"])
def test_integrity_check_reports_non_object_payload_without_crashing(conn, payload):
    conn.execute(
        """
        INSERT INTO event_log (event_type, payload, created_at)
        VALUES (?, ?, '2026-07-13T00:00:00.000Z')
        """,
        (response_outcomes.OUTCOME_EVENT, payload),
    )
    conn.commit()

    result = integrity.check(conn)

    assert result["ok"] is False
    assert any("payload must be a JSON object" in issue for issue in result["issues"])


def test_projection_schema_constrains_feedback_eligible_to_boolean_integer(conn):
    event_id = ledger.append(
        conn,
        response_outcomes.OUTCOME_EVENT,
        {
            "channel": "telegram",
            "outcome": "answered",
            "readings": [],
            "answer_mode": "core",
            "feedback_eligible": True,
        },
    )
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        conn.execute(
            """
            INSERT INTO response_outcome_log
                (response_id, channel, outcome, readings, answer_mode,
                 feedback_eligible, created_at)
            VALUES (?, 'telegram', 'answered', '[]', 'core', 2,
                    '2026-07-13T00:00:00.000Z')
            """,
            (event_id,),
        )


def test_schema_and_router_expose_both_projection_links(conn):
    assert integrity.validate_schema(conn) == []
    assert event_router.PROJEKTIONSZIELE[response_outcomes.OUTCOME_EVENT] == frozenset(
        {"response_outcome_log"}
    )
    assert event_router.PROJEKTIONSZIELE[response_outcomes.FEEDBACK_EVENT] == frozenset(
        {"response_feedback_log"}
    )
    assert event_router.REPLAY_PROJEKTIONSTABELLEN[:2] == (
        "response_feedback_log",
        "response_outcome_log",
    )

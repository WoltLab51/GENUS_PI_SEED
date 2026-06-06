import json

import pytest

from genus import event_router, ledger
from tests.conftest import observe_cpu_value


def test_append_creates_row(conn):
    event_id = ledger.append(conn, "observation_created", {"source": "x", "raw_value": 1, "unit": "n"})

    row = conn.execute("SELECT * FROM event_log WHERE id = ?", (event_id,)).fetchone()

    assert row["event_type"] == "observation_created"
    assert json.loads(row["payload"]) == {"source": "x", "raw_value": 1, "unit": "n"}


def test_append_does_not_commit(conn):
    ledger.append(conn, "observation_created", {"source": "x"})
    conn.rollback()

    count = conn.execute("SELECT COUNT(*) AS count FROM event_log").fetchone()["count"]

    assert count == 0


def test_event_log_is_append_only(conn):
    event_id = ledger.append(conn, "observation_created", {"source": "x"})

    with pytest.raises(Exception):
        conn.execute("UPDATE event_log SET event_type = 'changed' WHERE id = ?", (event_id,))
    with pytest.raises(Exception):
        conn.execute("DELETE FROM event_log WHERE id = ?", (event_id,))


def test_tail_returns_correct_count(conn):
    for i in range(30):
        ledger.append(conn, "observation_created", {"i": i})

    rows = ledger.tail(conn, n=10)

    assert len(rows) == 10
    assert rows[0]["payload"]["i"] == 20
    assert rows[-1]["payload"]["i"] == 29


def test_replay_rebuilds_identical_state(conn):
    for value in [92, 93, 94, 70, 50, 40, 30, 91, 92, 93]:
        observe_cpu_value(conn, value)

    before = snapshot(conn)
    summary = event_router.replay(conn)
    after = snapshot(conn)

    assert summary["events"] > 0
    assert after == before


def test_replay_delete_order_allows_foreign_keys(conn):
    conn.execute("PRAGMA foreign_keys = ON")
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    for _ in range(3):
        observe_cpu_value(conn, 40.0)

    summary = event_router.replay(conn)

    assert summary["inquiries"] == 1
    assert summary["proposals"] == 2


def snapshot(conn):
    beliefs = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, claim_key, claim_value, state, derivation,
                   supporting_events, contradicting_events, superseded_by
            FROM belief_projection
            ORDER BY id
            """
        ).fetchall()
    ]
    proposals = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, proposal_type, claim_key, claim_value,
                   source_belief, source_event, payload, state
            FROM proposal_log
            ORDER BY id
            """
        ).fetchall()
    ]
    return {"beliefs": beliefs, "proposals": proposals}

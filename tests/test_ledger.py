import json
import sqlite3

import pytest

from genus import db, event_router, ledger
from tests.conftest import observe_cpu_value


def test_append_creates_row(conn):
    event_id = ledger.append(conn, "observation_created", {"source": "x", "raw_value": 1, "unit": "n"})

    row = conn.execute("SELECT * FROM event_log WHERE id = ?", (event_id,)).fetchone()

    assert row["event_type"] == "observation_created"
    assert json.loads(row["payload"]) == {"source": "x", "raw_value": 1, "unit": "n"}


def test_schema_enables_foreign_keys(conn):
    enabled = conn.execute("PRAGMA foreign_keys").fetchone()[0]

    assert enabled == 1


def test_init_schema_adds_lifecycle_columns_to_existing_projection_tables():
    legacy = sqlite3.connect(":memory:")
    legacy.executescript(
        """
        CREATE TABLE proposal_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_type TEXT NOT NULL,
            claim_key TEXT NOT NULL,
            claim_value TEXT NOT NULL,
            source_belief INTEGER,
            source_event INTEGER,
            payload TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        );
        CREATE TABLE inquiry_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inquiry_type TEXT NOT NULL,
            claim_key TEXT NOT NULL,
            source_belief INTEGER,
            source_event INTEGER,
            question_key TEXT NOT NULL,
            payload TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            resolved_at TEXT
        );
        """
    )

    db.init_schema(legacy)
    proposal_columns = {
        row["name"] for row in legacy.execute("PRAGMA table_info(proposal_log)")
    }
    inquiry_columns = {
        row["name"] for row in legacy.execute("PRAGMA table_info(inquiry_log)")
    }
    legacy.close()

    assert {"decision", "reviewed_at"}.issubset(proposal_columns)
    assert "answer" in inquiry_columns


def test_init_schema_adds_sealing_columns_to_existing_event_log():
    legacy = sqlite3.connect(":memory:")
    legacy.row_factory = sqlite3.Row
    legacy.executescript(
        """
        CREATE TABLE event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT '2026-06-12T00:00:00.000Z'
        );
        INSERT INTO event_log (event_type, payload)
        VALUES ('observation_created', '{"source":"legacy"}');
        """
    )

    db.init_schema(legacy)
    columns = {row["name"] for row in legacy.execute("PRAGMA table_info(event_log)")}
    row = legacy.execute("SELECT prev_seal, seal FROM event_log WHERE id = 1").fetchone()
    legacy.close()

    assert {"prev_seal", "seal"}.issubset(columns)
    assert row["prev_seal"] is None
    assert row["seal"] is None


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

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from genus import projection
from genus.db import init_schema


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _instance(conn, claim_key, state, created_at, last_updated_at, supporting="[]"):
    conn.execute(
        "INSERT INTO belief_projection "
        "(claim_key, claim_value, state, derivation, supporting_events, "
        "created_at, last_updated_at) VALUES (?, 'v', ?, 'rule:t', ?, ?, ?)",
        (claim_key, state, supporting, created_at, last_updated_at),
    )
    conn.commit()


def test_stable_belief_gets_long_halflife():
    conn = _fresh()
    now = datetime.now(timezone.utc)
    _instance(conn, "test.inert", "active", _iso(now - timedelta(days=10)), _iso(now))

    hl = projection.learned_halflife(conn, "test.inert")
    assert hl is not None
    assert abs(hl - 10 * 86400) < 86400  # ~10 days, never flipped
    conn.close()


def test_volatile_belief_gets_short_halflife():
    conn = _fresh()
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=10)
    for i in range(4):  # four superseded instances ...
        _instance(conn, "test.flappy", "superseded",
                  _iso(start + timedelta(days=2 * i)), _iso(start + timedelta(days=2 * i)))
    _instance(conn, "test.flappy", "active",
              _iso(start + timedelta(days=8)), _iso(now))  # ... and the current one

    hl = projection.learned_halflife(conn, "test.flappy")
    # span ~10 days over 4 flips -> ~2.5 days, far shorter than the stable case
    assert abs(hl - (10 * 86400) / 4) < 86400
    conn.close()


def test_withholds_without_enough_tenure():
    conn = _fresh()
    now = datetime.now(timezone.utc)
    _instance(conn, "test.young", "active",
              _iso(now - timedelta(minutes=10)), _iso(now))

    assert projection.learned_halflife(conn, "test.young") is None
    conn.close()


def test_confidence_uses_learned_halflife_for_old_evidence():
    conn = _fresh()
    now = datetime.now(timezone.utc)
    conn.execute(
        "INSERT INTO event_log (event_type, payload, created_at) "
        "VALUES ('evidence_recorded', ?, ?)",
        (json.dumps({"metric_key": "x", "metric_value": 1.0}),
         _iso(now - timedelta(hours=2))),
    )
    eid = conn.execute("SELECT last_insert_rowid() AS r").fetchone()["r"]
    # a rock-stable belief (0 flips, 10-day span) supported by that 2h-old evidence
    _instance(conn, "test.inert", "active",
              _iso(now - timedelta(days=10)), _iso(now - timedelta(hours=2)),
              supporting=json.dumps([eid]))

    row = conn.execute(
        "SELECT * FROM belief_projection WHERE claim_key = 'test.inert'"
    ).fetchone()
    result = projection.belief_with_confidence(conn, row)

    # the learned ~10-day half-life keeps 2h-old evidence near full weight
    # (confidence ~0.5); the 30-min seed fallback would have decayed it to ~0.06.
    assert result["confidence"] > 0.4
    conn.close()

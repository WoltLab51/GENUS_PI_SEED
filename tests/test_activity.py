from genus import event_router
from tests.conftest import observe_activity_value


def test_active_creates_active_belief(conn):
    observe_activity_value(conn, 1.0)

    row = conn.execute(
        """
        SELECT * FROM belief_projection
        WHERE claim_key = 'system.activity' AND claim_value = 'active'
        """
    ).fetchone()

    assert row["state"] == "active"


def test_idle_creates_idle_belief(conn):
    observe_activity_value(conn, 0.0)

    row = conn.execute(
        """
        SELECT * FROM belief_projection
        WHERE claim_key = 'system.activity' AND claim_value = 'idle'
        """
    ).fetchone()

    assert row["state"] == "active"


def test_activity_change_supersedes_immediately(conn):
    observe_activity_value(conn, 1.0)
    written = observe_activity_value(conn, 0.0)

    rows = conn.execute(
        """
        SELECT * FROM belief_projection
        WHERE claim_key = 'system.activity'
        ORDER BY id
        """
    ).fetchall()
    weakened_count = conn.execute(
        "SELECT COUNT(*) AS count FROM event_log WHERE event_type = 'belief_weakened'"
    ).fetchone()["count"]

    assert written == ["evidence_recorded", "belief_superseded"]
    assert weakened_count == 0
    assert rows[0]["claim_value"] == "active"
    assert rows[0]["state"] == "superseded"
    assert rows[1]["claim_value"] == "idle"
    assert rows[1]["state"] == "active"


def test_activity_does_not_require_window(conn):
    written = observe_activity_value(conn, 1.0)

    assert "belief_created" in written


def test_activity_replay_stable(conn):
    for value in [1.0, 0.0, 1.0, 1.0, 0.0]:
        observe_activity_value(conn, value)

    before = snapshot_activity(conn)
    summary = event_router.replay(conn)
    after = snapshot_activity(conn)

    assert summary["active_beliefs"] == 1
    assert after == before


def snapshot_activity(conn):
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, claim_key, claim_value, state, supporting_events, superseded_by
            FROM belief_projection
            WHERE claim_key = 'system.activity'
            ORDER BY id
            """
        ).fetchall()
    ]

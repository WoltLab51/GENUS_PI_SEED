import json

from genus import event_router, integrity, projection
from tests.conftest import observe_activity_value


def _active_supporting(conn, claim_key="system.activity"):
    row = conn.execute(
        "SELECT supporting_events FROM belief_projection "
        "WHERE claim_key = ? AND state = 'active'",
        (claim_key,),
    ).fetchone()
    return json.loads(row["supporting_events"])


def test_supporting_events_are_bounded_to_the_window(monkeypatch, conn):
    monkeypatch.setattr(projection, "SUPPORTING_EVENTS_WINDOW", 5)
    for _ in range(20):  # one creation, then many confirmations
        observe_activity_value(conn, 1.0)

    ids = _active_supporting(conn)
    assert len(ids) == 5


def test_window_keeps_the_most_recent_events(monkeypatch, conn):
    monkeypatch.setattr(projection, "SUPPORTING_EVENTS_WINDOW", 5)
    for _ in range(20):
        observe_activity_value(conn, 1.0)

    ids = _active_supporting(conn)
    # the kept ids are the newest (largest), in order -- exactly the ones
    # confidence weights most heavily.
    assert ids == sorted(ids)
    newest = conn.execute(
        "SELECT id FROM event_log WHERE event_type = 'evidence_recorded' "
        "ORDER BY id DESC LIMIT 5"
    ).fetchall()
    assert set(ids) == {int(r["id"]) for r in newest}


def test_window_keeps_confidence_high(monkeypatch, conn):
    monkeypatch.setattr(projection, "SUPPORTING_EVENTS_WINDOW", 5)
    for _ in range(20):
        observe_activity_value(conn, 1.0)

    belief = next(
        b for b in projection.list_active_beliefs(conn)
        if b["claim_key"] == "system.activity"
    )
    # the count reflects the recent window, and recent evidence keeps it confident
    assert belief["supporting"] == 5
    assert belief["confidence"] > 0.7


def test_bounded_confirm_is_replay_stable(monkeypatch, conn):
    monkeypatch.setattr(projection, "SUPPORTING_EVENTS_WINDOW", 5)
    for _ in range(20):
        observe_activity_value(conn, 1.0)
    before = integrity.snapshot_projections(conn)

    event_router.replay(conn)
    after = integrity.snapshot_projections(conn)

    assert after == before
    assert integrity.check(conn)["ok"] is True

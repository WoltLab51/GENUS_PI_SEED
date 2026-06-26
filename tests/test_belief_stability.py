import json
import sqlite3

from genus import event_router, experience, integrity, ledger
from genus.db import init_schema


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


class _Ids:
    def __init__(self):
        self.n = 0

    def next(self) -> int:
        self.n += 1
        return self.n


def _emit_lifecycle(conn, ids: _Ids, claim_key: str, confirms: int, flips: int) -> None:
    # One creation, then `confirms` confirmations and `flips` supersessions, so
    # flip_rate = flips / (confirms + flips).
    bid = ids.next()
    ledger.append(
        conn,
        "belief_created",
        {
            "belief_id": bid,
            "claim_key": claim_key,
            "claim_value": "v0",
            "derivation": "rule:test",
            "supporting_events": [],
        },
    )
    for _ in range(confirms):
        ledger.append(conn, "belief_confirmed", {"belief_id": bid, "new_supporting_event": 1})
    for i in range(flips):
        nbid = ids.next()
        ledger.append(
            conn,
            "belief_superseded",
            {
                "old_belief_id": bid,
                "new_belief_id": nbid,
                "claim_key": claim_key,
                "claim_value": f"v{i + 1}",
                "derivation": "rule:test",
                "supporting_events": [],
                "reason": "test",
            },
        )
        bid = nbid
    conn.commit()


def _stability(conn, claim_key):
    row = conn.execute(
        "SELECT pattern, summary FROM experience_log "
        "WHERE subject_key = ? AND experience_type = 'BeliefStability'",
        (claim_key,),
    ).fetchone()
    if row is None:
        return None
    return json.loads(row["pattern"])


def test_belief_stability_classifies_relative_to_own_population():
    conn = _fresh()
    ids = _Ids()
    _emit_lifecycle(conn, ids, "alpha.stable", confirms=20, flips=0)   # rate 0.0
    _emit_lifecycle(conn, ids, "beta.volatile", confirms=5, flips=15)  # rate 0.75

    experience.scan(conn)

    alpha = _stability(conn, "alpha.stable")
    beta = _stability(conn, "beta.volatile")
    assert alpha["flip_rate"] == 0.0
    assert alpha["classification"] == "stable"
    assert beta["flip_rate"] == 0.75
    assert beta["classification"] == "volatile"
    conn.close()


def test_belief_stability_withholds_without_enough_history():
    conn = _fresh()
    ids = _Ids()
    _emit_lifecycle(conn, ids, "stable.long", confirms=20, flips=0)
    _emit_lifecycle(conn, ids, "short.lived", confirms=3, flips=2)  # 5 updates < MIN

    experience.scan(conn)

    # short.lived is below MIN_LIFECYCLE_UPDATES, leaving only one qualifying
    # belief -> no population to judge against -> withhold all.
    assert _stability(conn, "short.lived") is None
    assert _stability(conn, "stable.long") is None
    conn.close()


def test_belief_stability_withholds_without_spread():
    conn = _fresh()
    ids = _Ids()
    _emit_lifecycle(conn, ids, "calm.one", confirms=20, flips=0)
    _emit_lifecycle(conn, ids, "calm.two", confirms=30, flips=0)  # both rate 0.0

    experience.scan(conn)

    # No spread across the population -> the verdict would be vacuous -> withhold.
    assert _stability(conn, "calm.one") is None
    assert _stability(conn, "calm.two") is None
    conn.close()


def test_belief_stability_records_no_proposal():
    conn = _fresh()
    ids = _Ids()
    _emit_lifecycle(conn, ids, "alpha.stable", confirms=20, flips=0)
    _emit_lifecycle(conn, ids, "beta.volatile", confirms=5, flips=15)

    experience.scan(conn)

    # Slice 1 records knowledge only; it does not raise review work.
    proposals = conn.execute("SELECT COUNT(*) AS n FROM proposal_log").fetchone()
    assert proposals["n"] == 0
    conn.close()


def test_belief_stability_is_replay_stable_and_integrity_passes():
    conn = _fresh()
    ids = _Ids()
    _emit_lifecycle(conn, ids, "alpha.stable", confirms=20, flips=0)
    _emit_lifecycle(conn, ids, "beta.volatile", confirms=5, flips=15)
    experience.scan(conn)
    # Establish the canonical projection from the events (the synthetic helper
    # writes raw belief events without projecting), then test replay idempotency.
    event_router.replay(conn)
    before = integrity.snapshot_projections(conn)

    event_router.replay(conn)
    after = integrity.snapshot_projections(conn)

    assert after == before
    assert integrity.check(conn)["ok"] is True
    conn.close()


def test_cognition_registry_holds_both_detectors():
    names = {detector.__name__ for detector in experience.DETECTORS}
    assert "_activity_daily_rhythm_candidates" in names
    assert "_belief_stability_candidates" in names

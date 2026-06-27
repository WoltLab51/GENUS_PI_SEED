import sqlite3

from click.testing import CliRunner

from genus import cli, event_router, experience, ledger, query
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


def _emit_lifecycle(conn, ids, claim_key, confirms, flips):
    bid = ids.next()
    ledger.append(
        conn,
        "belief_created",
        {"belief_id": bid, "claim_key": claim_key, "claim_value": "v0",
         "derivation": "rule:test", "supporting_events": []},
    )
    for _ in range(confirms):
        ledger.append(conn, "belief_confirmed", {"belief_id": bid, "new_supporting_event": 1})
    for i in range(flips):
        nbid = ids.next()
        ledger.append(
            conn,
            "belief_superseded",
            {"old_belief_id": bid, "new_belief_id": nbid, "claim_key": claim_key,
             "claim_value": f"v{i + 1}", "derivation": "rule:test",
             "supporting_events": [], "reason": "test"},
        )
        bid = nbid
    conn.commit()


def _flip(conn, ids, claim_key):
    ledger.append(
        conn,
        "belief_superseded",
        {"old_belief_id": 0, "new_belief_id": ids.next(), "claim_key": claim_key,
         "claim_value": "flipped", "derivation": "rule:test",
         "supporting_events": [], "reason": "test"},
    )
    conn.commit()


def test_calibration_empty_without_judgments():
    conn = _fresh()
    report = query.calibration(conn)
    assert report["stable_count"] == 0
    assert report["stable_judgment_accuracy"] is None
    conn.close()


def test_calibration_perfect_when_nothing_betrays_its_judgment():
    conn = _fresh()
    ids = _Ids()
    _emit_lifecycle(conn, ids, "alpha.stable", confirms=20, flips=0)
    _emit_lifecycle(conn, ids, "beta.volatile", confirms=5, flips=15)
    experience.scan(conn)

    report = query.calibration(conn)
    assert report["stable_count"] == 1
    assert report["volatile_count"] == 1
    assert report["betrayed"] == []
    assert report["stable_judgment_accuracy"] == 1.0
    # the judgment discriminates: volatile beliefs flip more than stable ones
    assert report["volatile_mean_flip_rate"] > report["stable_mean_flip_rate"]
    conn.close()


def test_calibration_drops_when_a_stable_belief_betrays_its_judgment():
    conn = _fresh()
    ids = _Ids()
    _emit_lifecycle(conn, ids, "alpha.stable", confirms=20, flips=0)
    _emit_lifecycle(conn, ids, "beta.volatile", confirms=5, flips=15)
    experience.scan(conn)  # alpha judged stable

    _flip(conn, ids, "alpha.stable")  # a 'stable' belief flips -> surprise
    event_router.replay(conn)
    experience.scan(conn)  # raises the StabilityInquiry

    report = query.calibration(conn)
    assert "alpha.stable" in report["betrayed"]
    assert report["stable_judgment_accuracy"] < 1.0
    conn.close()


def test_calibration_cli_runs(monkeypatch):
    conn = _fresh()
    ids = _Ids()
    _emit_lifecycle(conn, ids, "alpha.stable", confirms=20, flips=0)
    _emit_lifecycle(conn, ids, "beta.volatile", confirms=5, flips=15)
    experience.scan(conn)

    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["calibration"])

    assert result.exit_code == 0, result.output
    assert "stable-judgment accuracy" in result.output

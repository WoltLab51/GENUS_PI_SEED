import sqlite3

from click.testing import CliRunner

from genus import cli, experience, ledger, query
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


def test_surprisal_empty():
    conn = _fresh()
    assert query.surprisal(conn) == []
    conn.close()


def test_stable_flip_carries_more_bits_than_volatile_flip():
    conn = _fresh()
    ids = _Ids()
    _emit_lifecycle(conn, ids, "alpha.stable", confirms=40, flips=0)
    _emit_lifecycle(conn, ids, "beta.volatile", confirms=5, flips=15)
    experience.scan(conn)

    by_key = {r["subject_key"]: r for r in query.surprisal(conn)}
    # a rock-stable belief flipping is shocking; a volatile one flipping is expected
    assert by_key["alpha.stable"]["surprise_bits"] > by_key["beta.volatile"]["surprise_bits"]
    conn.close()


def test_surprisal_ranked_descending():
    conn = _fresh()
    ids = _Ids()
    _emit_lifecycle(conn, ids, "alpha.stable", confirms=40, flips=0)
    _emit_lifecycle(conn, ids, "beta.volatile", confirms=5, flips=15)
    experience.scan(conn)

    rows = query.surprisal(conn)
    bits = [r["surprise_bits"] for r in rows]
    assert bits == sorted(bits, reverse=True)
    conn.close()


def test_surprisal_cli_runs(monkeypatch):
    conn = _fresh()
    ids = _Ids()
    _emit_lifecycle(conn, ids, "alpha.stable", confirms=40, flips=0)
    _emit_lifecycle(conn, ids, "beta.volatile", confirms=5, flips=15)
    experience.scan(conn)

    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["surprisal"])

    assert result.exit_code == 0, result.output
    assert "bits" in result.output

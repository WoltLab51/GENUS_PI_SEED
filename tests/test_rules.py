import inspect

from genus import rules
from tests.conftest import observe_cpu_value


def test_window_below_threshold_does_not_create_belief(conn):
    observe_cpu_value(conn, 92.0)
    observe_cpu_value(conn, 92.0)

    count = conn.execute("SELECT COUNT(*) AS count FROM belief_projection").fetchone()["count"]

    assert count == 0


def test_mixed_window_weakens_belief_not_supersedes(conn):
    for _ in range(3):
        observe_cpu_value(conn, 92.0)

    written = observe_cpu_value(conn, 40.0)
    row = conn.execute("SELECT * FROM belief_projection WHERE claim_value = 'high'").fetchone()

    assert "belief_weakened" in written
    assert "belief_superseded" not in written
    assert row["state"] == "active"


def test_contradiction_creates_proposal(conn):
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    for _ in range(3):
        observe_cpu_value(conn, 40.0)

    rows = conn.execute("SELECT * FROM proposal_log ORDER BY id").fetchall()

    assert len(rows) == 2
    assert {row["proposal_type"] for row in rows} == {"ResourceProposal"}


def test_derivation_is_always_set(conn):
    for _ in range(3):
        observe_cpu_value(conn, 92.0)

    rows = conn.execute("SELECT derivation FROM belief_projection").fetchall()

    assert rows
    assert all(row["derivation"] == rules.DERIVATION for row in rows)


def test_no_http_in_rules():
    source = inspect.getsource(rules)

    forbidden = ["requests", "httpx", "aiohttp", "urllib"]
    assert all(word not in source for word in forbidden)


def test_thresholds_are_binding():
    assert rules.HIGH_THRESHOLD == 80.0
    assert rules.LOW_THRESHOLD == 60.0
    assert rules.WINDOW_SIZE == 3

from click.testing import CliRunner

from genus import cli, rules
from genus.sensor import mock_memory
from tests.conftest import observe_cpu_value, observe_memory_value


def test_high_memory_creates_memory_belief(conn):
    for _ in range(3):
        observe_memory_value(conn, 91.0)

    row = conn.execute(
        """
        SELECT * FROM belief_projection
        WHERE claim_key = 'system.memory' AND claim_value = 'high'
        """
    ).fetchone()

    assert row["state"] == "active"
    assert row["derivation"] == rules.MEMORY_DERIVATION


def test_low_after_high_memory_supersedes_memory_belief(conn):
    for _ in range(3):
        observe_memory_value(conn, 91.0)
    old = conn.execute(
        "SELECT * FROM belief_projection WHERE claim_key = 'system.memory'"
    ).fetchone()

    for _ in range(3):
        observe_memory_value(conn, 50.0)

    old_after = conn.execute(
        "SELECT * FROM belief_projection WHERE id = ?",
        (old["id"],),
    ).fetchone()
    new = conn.execute(
        """
        SELECT * FROM belief_projection
        WHERE claim_key = 'system.memory' AND claim_value = 'normal'
        """
    ).fetchone()

    assert old_after["state"] == "superseded"
    assert new["state"] == "active"
    assert old_after["superseded_by"] == new["id"]


def test_cpu_and_memory_windows_are_independent(conn):
    for _ in range(2):
        observe_cpu_value(conn, 92.0)
    for _ in range(3):
        observe_memory_value(conn, 91.0)

    cpu_count = conn.execute(
        "SELECT COUNT(*) AS count FROM belief_projection WHERE claim_key = 'system.load'"
    ).fetchone()["count"]
    memory_count = conn.execute(
        "SELECT COUNT(*) AS count FROM belief_projection WHERE claim_key = 'system.memory'"
    ).fetchone()["count"]

    assert cpu_count == 0
    assert memory_count == 1


def test_observe_memory_cli_writes_base_events(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    monkeypatch.setattr(cli.sensor, "read_memory", lambda: mock_memory(91.0))

    result = CliRunner().invoke(cli.main, ["observe-memory"])

    assert result.exit_code == 0
    assert "[OBS] MEM: 91.0%" in result.output
    rows = conn.execute("SELECT event_type FROM event_log ORDER BY id").fetchall()
    assert [row["event_type"] for row in rows] == [
        "observation_created",
        "evidence_recorded",
    ]


def test_memory_thresholds_are_binding():
    assert rules.MEMORY_HIGH_THRESHOLD == 85.0
    assert rules.MEMORY_LOW_THRESHOLD == 70.0

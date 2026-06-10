from click.testing import CliRunner

from genus import cli
from tests.conftest import observe_cpu_value, observe_temperature_value


def test_high_temp_creates_belief(conn):
    for _ in range(3):
        observe_temperature_value(conn, 80.0)

    row = conn.execute(
        """
        SELECT * FROM belief_projection
        WHERE claim_key = 'system.temperature' AND claim_value = 'high'
        """
    ).fetchone()

    assert row["state"] == "active"


def test_temperature_unavailable_graceful(monkeypatch, cli_conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    monkeypatch.setattr(cli.sensor, "read_temperature", lambda: None)

    result = CliRunner().invoke(cli.main, ["observe-temperature"])

    assert result.exit_code == 0
    assert "not available" in result.output


def test_temperature_and_cpu_beliefs_can_coexist(conn):
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    for _ in range(3):
        observe_temperature_value(conn, 80.0)

    rows = conn.execute(
        """
        SELECT claim_key, claim_value, state FROM belief_projection
        WHERE state = 'active'
        ORDER BY claim_key
        """
    ).fetchall()

    assert [(row["claim_key"], row["claim_value"]) for row in rows] == [
        ("system.load", "high"),
        ("system.temperature", "high"),
    ]

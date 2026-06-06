from click.testing import CliRunner

from genus import cli
from genus.sensor import mock_cpu, mock_memory
from tests.conftest import observe_cpu_value


def test_observe_cpu_writes_two_base_events(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    monkeypatch.setattr(cli.sensor, "read_cpu", lambda: mock_cpu(92.0))

    result = CliRunner().invoke(cli.main, ["observe-cpu"])

    assert result.exit_code == 0
    rows = conn.execute("SELECT event_type FROM event_log ORDER BY id").fetchall()
    assert [row["event_type"] for row in rows] == [
        "observation_created",
        "evidence_recorded",
    ]


def test_observe_memory_writes_two_base_events(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    monkeypatch.setattr(cli.sensor, "read_memory", lambda: mock_memory(91.0))

    result = CliRunner().invoke(cli.main, ["observe-memory"])

    assert result.exit_code == 0
    rows = conn.execute("SELECT event_type FROM event_log ORDER BY id").fetchall()
    assert [row["event_type"] for row in rows] == [
        "observation_created",
        "evidence_recorded",
    ]


def test_beliefs_show_returns_active_only(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    for _ in range(3):
        observe_cpu_value(conn, 40.0)

    result = CliRunner().invoke(cli.main, ["beliefs", "show"])

    assert result.exit_code == 0
    assert "system.load  normal" in result.output
    assert "system.load  high" not in result.output


def test_proposals_list_shows_pending(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    for _ in range(3):
        observe_cpu_value(conn, 92.0)

    result = CliRunner().invoke(cli.main, ["proposals", "list"])

    assert result.exit_code == 0
    assert "ResourceProposal" in result.output
    assert "pending" in result.output


def test_replay_command_exits_zero(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    for value in [92, 93, 94, 40, 41]:
        observe_cpu_value(conn, value)

    result = CliRunner().invoke(cli.main, ["replay"])

    assert result.exit_code == 0
    assert "State matches current projection" in result.output


def test_integrity_check_command_exits_zero(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    for value in [92, 93, 94]:
        observe_cpu_value(conn, value)

    result = CliRunner().invoke(cli.main, ["integrity", "check"])

    assert result.exit_code == 0
    assert "[INTEGRITY] OK" in result.output

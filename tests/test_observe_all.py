from click.testing import CliRunner

from genus import cli
from genus.sensor import (
    mock_activity,
    mock_cpu,
    mock_disk,
    mock_memory,
    mock_temperature,
)


def test_observe_all_writes_base_events_for_each_sensor(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    monkeypatch.setattr(cli.sensor, "read_cpu", lambda: mock_cpu(42.0))
    monkeypatch.setattr(cli.sensor, "read_memory", lambda: mock_memory(43.0))
    monkeypatch.setattr(cli.sensor, "read_disk", lambda: mock_disk(44.0))
    monkeypatch.setattr(cli.sensor, "read_activity", lambda: mock_activity(1.0))
    monkeypatch.setattr(cli.sensor, "read_temperature", lambda: mock_temperature(45.0))

    result = CliRunner().invoke(cli.main, ["observe-all"])

    assert result.exit_code == 0
    observation_count = conn.execute(
        "SELECT COUNT(*) AS count FROM event_log WHERE event_type = 'observation_created'"
    ).fetchone()["count"]
    evidence_count = conn.execute(
        "SELECT COUNT(*) AS count FROM event_log WHERE event_type = 'evidence_recorded'"
    ).fetchone()["count"]

    assert observation_count == 5
    assert evidence_count == 5


def test_observe_all_exits_zero_when_temperature_unavailable(monkeypatch, cli_conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    monkeypatch.setattr(cli.sensor, "read_cpu", lambda: mock_cpu(42.0))
    monkeypatch.setattr(cli.sensor, "read_memory", lambda: mock_memory(43.0))
    monkeypatch.setattr(cli.sensor, "read_disk", lambda: mock_disk(44.0))
    monkeypatch.setattr(cli.sensor, "read_activity", lambda: mock_activity(1.0))
    monkeypatch.setattr(cli.sensor, "read_temperature", lambda: None)

    result = CliRunner().invoke(cli.main, ["observe-all"])

    assert result.exit_code == 0
    assert "TMP: not available" in result.output

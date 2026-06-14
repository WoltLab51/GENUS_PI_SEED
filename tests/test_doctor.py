from click.testing import CliRunner

from genus import cli, ledger, sealing
from genus.sensor import mock_activity, mock_cpu, mock_disk, mock_memory, mock_temperature


def _patch_sensors(monkeypatch):
    monkeypatch.setattr(cli.sensor, "read_cpu", lambda: mock_cpu(12.0))
    monkeypatch.setattr(cli.sensor, "read_memory", lambda: mock_memory(34.0))
    monkeypatch.setattr(cli.sensor, "read_disk", lambda: mock_disk(56.0))
    monkeypatch.setattr(cli.sensor, "read_activity", lambda: mock_activity(1.0))
    monkeypatch.setattr(cli.sensor, "read_temperature", lambda: mock_temperature(42.0))


def test_doctor_exits_zero_with_warnings_and_writes_no_events(
    monkeypatch,
    cli_conn,
    conn,
):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    _patch_sensors(monkeypatch)

    result = CliRunner().invoke(cli.main, ["doctor"])

    assert result.exit_code == 0
    assert "[OK] database:" in result.output
    assert "[WARN] sealing:" in result.output
    assert "[WARN] core-id:" in result.output
    count = conn.execute("SELECT COUNT(*) AS count FROM event_log").fetchone()["count"]
    assert count == 0


def test_doctor_reports_sealing_and_core_id(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    _patch_sensors(monkeypatch)
    sealing.open_epoch(conn)

    result = CliRunner().invoke(
        cli.main,
        ["doctor"],
        env={"GENUS_CORE_ID": "pi-core"},
    )

    assert result.exit_code == 0
    assert "[OK] sealing:" in result.output
    assert "[OK] core-id: GENUS_CORE_ID=pi-core" in result.output
    assert "[OK] forbidden-model-imports: none" in result.output
    assert "[OK] forbidden-network-imports: none" in result.output


def test_doctor_fails_on_integrity_error(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    _patch_sensors(monkeypatch)
    ledger.append(conn, "observation_created", {"source": "mock"})

    result = CliRunner().invoke(cli.main, ["doctor"])

    assert result.exit_code != 0
    assert "[FAIL] integrity:" in result.output

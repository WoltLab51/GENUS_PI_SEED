from click.testing import CliRunner

from genus import cli, hand, ledger, sealing
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
    monkeypatch.setattr(cli, "get_diagnostic_conn", lambda: cli_conn)
    monkeypatch.delenv("GENUS_CORE_ID", raising=False)
    _patch_sensors(monkeypatch)

    result = CliRunner().invoke(cli.main, ["doctor"])

    assert result.exit_code == 0
    assert "[OK] database:" in result.output
    assert "[OK] ledger-storage:" in result.output
    assert "events_24h=" in result.output
    assert "estimated_daily_growth_bytes=" in result.output
    assert "check_ms=" in result.output
    assert "[WARN] sealing:" in result.output
    assert "[WARN] core-id:" in result.output
    count = conn.execute("SELECT COUNT(*) AS count FROM event_log").fetchone()["count"]
    assert count == 0


def test_doctor_reports_sealing_and_core_id(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_diagnostic_conn", lambda: cli_conn)
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
    monkeypatch.setattr(cli, "get_diagnostic_conn", lambda: cli_conn)
    _patch_sensors(monkeypatch)
    ledger.append(conn, "observation_created", {"source": "mock"})

    result = CliRunner().invoke(cli.main, ["doctor"])

    assert result.exit_code != 0
    assert "[FAIL] integrity:" in result.output


def test_doctor_warnt_bei_ueberfaelliger_ungesendeter_hand(monkeypatch, cli_conn, conn):
    # Herzschlag-Waechter der ersten Hand: eine freigegebene, laengst faellige, aber ungesendete
    # Erinnerung -> [WARN] (der Sende-Tick steht offenbar still). WARN, KEIN FAIL: reparabel,
    # doctor bleibt gruen (exit 0). Und: hand-Ereignisse brechen die Integritaet NICHT (mehr).
    monkeypatch.setattr(cli, "get_diagnostic_conn", lambda: cli_conn)
    monkeypatch.delenv("GENUS_CORE_ID", raising=False)
    _patch_sensors(monkeypatch)
    hid = hand.vorschlagen(conn, "nachricht", "laengst faellig",
                           faellig_um="2000-01-01T00:00:00")["hand_id"]
    hand.bestaetigen(conn, hid)

    result = CliRunner().invoke(cli.main, ["doctor"])

    assert result.exit_code == 0                       # WARN, kein FAIL -> doctor bleibt gruen
    assert "[WARN] hand-faellig:" in result.output
    assert "[OK] integrity:" in result.output          # hand-Ereignisse sind dem Vertrag jetzt bekannt


def test_doctor_hand_check_ok_ohne_ueberfaellige(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_diagnostic_conn", lambda: cli_conn)
    _patch_sensors(monkeypatch)

    result = CliRunner().invoke(cli.main, ["doctor"])

    assert result.exit_code == 0
    assert "[OK] hand-faellig:" in result.output

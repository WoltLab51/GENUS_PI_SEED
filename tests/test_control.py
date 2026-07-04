from click.testing import CliRunner

from genus import cli, control


def test_pause_resume_cycle(tmp_path, monkeypatch):
    monkeypatch.setenv("GENUS_PAUSE_FILE", str(tmp_path / "paused"))
    assert control.is_paused() is False
    control.pause("maintenance")
    assert control.is_paused() is True
    assert control.reason() == "maintenance"
    assert control.resume() is True
    assert control.is_paused() is False
    assert control.resume() is False  # idempotent


def test_pause_cli_round_trip(tmp_path, monkeypatch):
    flag = tmp_path / "paused"
    monkeypatch.setenv("GENUS_PAUSE_FILE", str(flag))
    runner = CliRunner()

    running = runner.invoke(cli.main, ["paused"])
    assert running.exit_code == 1 and "running" in running.output  # exit 1 = running

    paused = runner.invoke(cli.main, ["pause", "--reason", "deploy"])
    assert paused.exit_code == 0 and "PAUSED" in paused.output
    assert flag.exists()

    status = runner.invoke(cli.main, ["paused"])
    assert status.exit_code == 0 and "deploy" in status.output  # exit 0 = paused

    resumed = runner.invoke(cli.main, ["resume"])
    assert "resumed" in resumed.output
    assert not flag.exists()


def test_observe_all_skips_when_paused(tmp_path, monkeypatch):
    monkeypatch.setenv("GENUS_PAUSE_FILE", str(tmp_path / "paused"))
    control.pause()
    result = CliRunner().invoke(cli.main, ["observe-all"])
    assert result.exit_code == 0
    assert "paused" in result.output.lower()  # no observations written while paused


# --- der Pause-VERTRAG als Klassen-Gate (Fund 2026-07-04: state refresh + clock-check
# --- ignorierten den Schalter; Klasse fixen, nicht Instanz) ---------------------------


def test_state_refresh_respektiert_die_pause(monkeypatch, tmp_path):
    flag = tmp_path / "paused"
    monkeypatch.setenv("GENUS_PAUSE_FILE", str(flag))
    monkeypatch.setenv("GENUS_DB_PATH", str(tmp_path / "genus.sqlite3"))
    control.pause("test")
    result = CliRunner().invoke(cli.main, ["state", "refresh"])
    assert result.exit_code == 0 and "paused" in result.output


def test_pause_vertrag_jedes_autonome_skript_prueft_den_schalter():
    # Struktur-Gate wie test_membrane_purity: jedes per Cron/Daemon laufende Skript muss
    # den Pause-Schalter pruefen -- ein neues autonomes Skript ohne Pruefung bricht CI.
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    autonome_skripte = (
        "observe_weather.sh", "observe_weather_second.sh", "pi_learn.sh",
        "pi_network_watchdog.sh", "pi_clock_check.sh",
    )
    for name in autonome_skripte:
        text = (root / "deploy" / name).read_text(encoding="utf-8")
        assert "paused" in text, f"{name} prueft den Pause-Schalter nicht"


def test_deploy_pausiert_und_weckt_garantiert_wieder():
    # pi_deploy.sh pausiert fuer die Selbst-Checks (Replay-Wettlauf-Fund 2026-07-04)
    # und traegt ein trap-resume, das auch bei einem Fehler feuert.
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    text = (root / "deploy" / "pi_deploy.sh").read_text(encoding="utf-8")
    assert "genus pause" in text
    assert "trap" in text and "resume" in text

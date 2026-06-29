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

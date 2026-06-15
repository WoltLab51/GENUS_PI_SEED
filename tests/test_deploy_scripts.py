from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cron_installation_writes_timestamped_ticks():
    script = (ROOT / "deploy" / "pi_install_cron.sh").read_text(encoding="utf-8")

    assert "[TICK] observe-all" in script
    assert "[TICK] state-refresh" in script
    assert "[TICK] experience-scan" in script
    assert "[TICK] doctor" in script
    assert "[TICK] status-publish" in script
    assert r"date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ" in script


def test_network_watchdog_records_operation_events_and_governed_recovery():
    watchdog = (ROOT / "deploy" / "pi_network_watchdog.sh").read_text(
        encoding="utf-8"
    )
    installer = (ROOT / "deploy" / "pi_install_network_watchdog.sh").read_text(
        encoding="utf-8"
    )

    assert "operation network-check" in watchdog
    assert "operation recovery-result" in watchdog
    assert "--action \"$action\"" in watchdog
    assert "systemctl reboot" in watchdog
    assert "genus-network-watchdog.service" in installer
    assert "OnUnitActiveSec=5min" in installer
    assert "GENUS_USER" in installer

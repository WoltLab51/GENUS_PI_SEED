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

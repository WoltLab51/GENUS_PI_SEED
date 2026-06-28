import importlib.util
import json
from pathlib import Path

from genus import db, ledger, sealing


EXPORT_SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "export_pi_status.py"


def _load_export_module():
    spec = importlib.util.spec_from_file_location("export_pi_status", EXPORT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _seed_db(path: Path) -> None:
    conn = db.connect(path)
    try:
        sealing.open_epoch(conn)
        ledger.append(
            conn,
            "observation_created",
            {"source": "test", "raw_value": 1.0, "unit": "n"},
        )
        conn.commit()
    finally:
        conn.close()


def test_public_status_omits_local_paths_and_recent_event_timeline(
    monkeypatch,
    tmp_path,
):
    database = tmp_path / "genus.sqlite3"
    output = tmp_path / "latest.json"
    _seed_db(database)
    monkeypatch.setenv("GENUS_CORE_ID", "pi-core")
    monkeypatch.setenv("GENUS_DB_PATH", str(database))
    monkeypatch.setenv("GENUS_SEED_COMMIT", "abc123")
    monkeypatch.setattr("sys.argv", ["export_pi_status.py", str(output)])

    assert _load_export_module().main() == 0

    status = json.loads(output.read_text(encoding="utf-8"))
    serialized = json.dumps(status, sort_keys=True)
    assert status["schema"] == "genus-pi-status-v1"
    assert status["ok"] is True
    assert status["core_id"] == "pi-core"
    assert status["seed_commit"] == "abc123"
    assert status["privacy"] == {
        "profile": "public-minimal-v2",
        "redacted": ["local_paths", "raw_doctor", "latest_events"],
    }
    # aggregate, privacy-safe self-knowledge: calibration + per-path learning
    assert "calibration" in status["cognition"]
    assert "learning" in status["cognition"]
    assert set(status["cognition"]["calibration"]) == {
        "stable_judgments",
        "held",
        "accuracy",
        "discrimination",
    }
    assert isinstance(status["cognition"]["learning"], list)
    assert "latest_events" not in status
    assert "doctor" not in status
    assert str(tmp_path) not in serialized
    assert "/home/" not in serialized
    assert "C:\\" not in serialized

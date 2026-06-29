"""Pause control — one flag that freezes all AUTONOMOUS activity.

`genus pause` writes a marker file (next to the ledger); every autonomous entry point
(the sensor tick, the membranes, the background learner) checks it and skips while it is
present. Reads and manual commands keep working, and the ledger is untouched -- pausing
just stops new autonomous writes. `genus resume` removes the marker. This is the clean
"stop GENUS" switch and the gate the background learner needs from birth.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path


def flag_path() -> Path:
    """Where the pause marker lives -- next to the ledger (~/.genus/paused), or an explicit
    GENUS_PAUSE_FILE override (used by tests)."""
    override = os.environ.get("GENUS_PAUSE_FILE")
    if override:
        return Path(override)
    db = os.environ.get("GENUS_DB_PATH")
    base = Path(db).parent if db and db != ":memory:" else Path(os.path.expanduser("~"), ".genus")
    return base / "paused"


def is_paused() -> bool:
    return flag_path().exists()


def pause(reason: str = "") -> Path:
    p = flag_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    p.write_text(f"{stamp}\t{reason}\n", encoding="utf-8")
    return p


def resume() -> bool:
    p = flag_path()
    if p.exists():
        p.unlink()
        return True
    return False


def reason() -> str:
    p = flag_path()
    if not p.exists():
        return ""
    try:
        parts = p.read_text(encoding="utf-8").strip().split("\t", 1)
        return parts[1] if len(parts) > 1 else ""
    except OSError:
        return ""

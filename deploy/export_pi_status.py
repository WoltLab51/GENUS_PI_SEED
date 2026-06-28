from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from genus import db, integrity, learning, query, sealing


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: export_pi_status.py OUTPUT_PATH", file=sys.stderr)
        return 2

    core_id = os.environ.get("GENUS_CORE_ID", "").strip()
    if not core_id:
        print("GENUS_CORE_ID is required", file=sys.stderr)
        return 2

    db_path = os.environ.get("GENUS_DB_PATH", "genus.sqlite3")
    output_path = Path(sys.argv[1])
    conn = db.connect(db_path)
    try:
        check = integrity.check(conn)
        head = sealing.head(conn)
        status = {
            "schema": "genus-pi-status-v1",
            "core_id": core_id,
            "generated_at": _now_utc(),
            "seed_commit": os.environ.get("GENUS_SEED_COMMIT"),
            "ok": check["ok"],
            "issues": check["issues"],
            "counts": {
                "events": check["events"],
                "active_beliefs": check["active_beliefs"],
                "proposals": check["proposals"],
                "inquiries": check["inquiries"],
                "experiences": check["experiences"],
                "active_states": check["active_states"],
                "governance_decisions": check["governance_decisions"],
                "active_rules": check["active_rules"],
            },
            "sealing": _seal_summary(head),
            "cognition": _cognition(conn),
            "privacy": {
                "profile": "public-minimal-v2",
                "redacted": ["local_paths", "raw_doctor", "latest_events"],
            },
        }
    finally:
        conn.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(status, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


def _round(value: float | None) -> float | None:
    return round(value, 3) if value is not None else None


def _cognition(conn) -> dict:
    # Aggregate, privacy-safe self-knowledge for the public status: how honest is
    # GENUS's confidence (calibration), and how is each 24/7 learning path doing.
    # Only counts and errors -- no values, paths, or event detail. The unreliable
    # binary "improving" verdict is left out; the early->recent errors tell the
    # honest trajectory.
    cal = query.calibration(conn)
    discrimination = None
    if cal["stable_mean_flip_rate"] is not None and cal["volatile_mean_flip_rate"] is not None:
        discrimination = round(cal["volatile_mean_flip_rate"] - cal["stable_mean_flip_rate"], 3)
    return {
        "calibration": {
            "stable_judgments": cal["stable_count"],
            "held": cal["stable_count"] - len(cal["betrayed"]),
            "accuracy": _round(cal["stable_judgment_accuracy"]),
            "discrimination": discrimination,
        },
        "learning": [
            {
                "metric_key": curve["metric_key"],
                "scored": curve["scored"],
                "mean_error": _round(curve["mean_error"]),
                "early_error": _round(curve["early_mean_error"]),
                "recent_error": _round(curve["recent_mean_error"]),
            }
            for curve in learning.curves(conn)
        ],
    }


def _seal_summary(head: dict | None) -> dict:
    if head is None:
        return {"active": False, "head_event_id": None, "head": None}
    return {
        "active": True,
        "algo": sealing.ALGO,
        "head_event_id": int(head["id"]),
        "head_event_type": head["event_type"],
        "head_created_at": head["created_at"],
        "head": head["seal"],
    }


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from genus import db, integrity, sealing


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
            "privacy": {
                "profile": "public-minimal-v1",
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

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from genus import integrity, learning, query, sealing, startup


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
    conn = startup.connect(db_path)
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
    # A daily time-series so the learning journey is visible over days, plus a
    # human-readable rendering -- both alongside latest.json, no new privacy surface.
    history = _update_history(output_path.parent / "history.jsonl", _history_entry(status))
    (output_path.parent / "STATUS.md").write_text(
        _render_markdown(status, history), encoding="utf-8"
    )
    return 0


def _round(value: float | None) -> float | None:
    return round(value, 3) if value is not None else None


def _cognition(conn) -> dict:
    # Aggregate, privacy-safe self-knowledge for the public status: how honest is
    # GENUS's confidence (calibration), and how is each 24/7 learning path doing. Only
    # counts, errors, and forecast skill -- no values, paths, or event detail. Skill
    # (1 - model/naive error) honestly says whether a path learned real structure
    # (>0) or the signal is too flat to learn (~0).
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
                "skill": curve["skill"],
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


def _history_entry(status: dict) -> dict:
    cal = status["cognition"]["calibration"]
    return {
        "date": status["generated_at"][:10],
        "generated_at": status["generated_at"],
        "ok": status["ok"],
        "events": status["counts"]["events"],
        "active_beliefs": status["counts"]["active_beliefs"],
        "experiences": status["counts"]["experiences"],
        "calibration_accuracy": cal["accuracy"],
        "calibration_held": cal["held"],
        "calibration_stable": cal["stable_judgments"],
        "learning": {
            curve["metric_key"]: {
                "scored": curve["scored"],
                "mean_error": curve["mean_error"],
                "skill": curve["skill"],
            }
            for curve in status["cognition"]["learning"]
        },
    }


def _read_history(history_path: Path) -> list[dict]:
    if not history_path.exists():
        return []
    entries = []
    for line in history_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _update_history(history_path: Path, entry: dict) -> list[dict]:
    # One entry per calendar day (the most recent publish wins), so the series is a
    # clean daily trend even if the status is published more than once that day.
    entries = [e for e in _read_history(history_path) if e.get("date") != entry["date"]]
    entries.append(entry)
    entries.sort(key=lambda e: e.get("generated_at", ""))
    history_path.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n",
        encoding="utf-8",
    )
    return entries


def _render_markdown(status: dict, history: list[dict]) -> str:
    counts = status["counts"]
    cal = status["cognition"]["calibration"]
    learning = status["cognition"]["learning"]
    head = (status["sealing"].get("head") or "")[:16]
    out = [
        f"# GENUS · {status['core_id']}",
        "",
        f"**{'healthy ✓' if status['ok'] else 'ISSUES ✗'}** · seed "
        f"`{status.get('seed_commit') or '?'}` · generated `{status['generated_at']}`",
        "",
        "> Auto-generated public status — aggregate health only, no values, paths, or event detail.",
        "",
        "## Health",
        "",
        f"- events **{counts['events']}** · beliefs **{counts['active_beliefs']}** · "
        f"experiences **{counts['experiences']}** · proposals {counts['proposals']} · "
        f"rules {counts['active_rules']} · governance {counts['governance_decisions']}",
        f"- sealing head `{head}…` (event {status['sealing'].get('head_event_id')})",
        "",
        "## Self-knowledge",
        "",
    ]
    if cal["stable_judgments"]:
        disc = cal["discrimination"]
        out.append(
            f"**Calibration** — {cal['held']}/{cal['stable_judgments']} stable judgments held · "
            f"accuracy **{cal['accuracy']}**"
            + (f" · discriminates (+{disc})" if disc is not None else "")
            + " — *does GENUS know that it knows?*"
        )
    else:
        out.append("**Calibration** — no stability judgments yet.")
    out += ["", "**Learning** — 24/7 forecast paths (predict → self-test → score):", ""]
    if learning:
        out += [
            "| metric | scored | mean error | skill |",
            "| --- | ---: | ---: | ---: |",
        ]
        for curve in learning:
            skill = curve["skill"]
            out.append(
                f"| `{curve['metric_key']}` | {curve['scored']} | {curve['mean_error']} | "
                f"{'—' if skill is None else f'{skill:+.2f}'} |"
            )
        out += [
            "",
            "_skill = how much better than naive (guessing the mean): >0 learned real "
            "structure · ~0 the signal is too flat to learn · <0 worse than naive._",
        ]
    else:
        out.append("_warming up — no scored forecasts yet._")
    if len(history) >= 2:
        out += [
            "",
            "## Trend (last days)",
            "",
            "| day | events | beliefs | calib. | temp. err |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for entry in history[-7:]:
            temp = entry.get("learning", {}).get("system.temperature", {}).get("mean_error", "—")
            out.append(
                f"| {entry['date']} | {entry['events']} | {entry['active_beliefs']} | "
                f"{entry.get('calibration_accuracy', '—')} | {temp} |"
            )
    out += [
        "",
        "## Verify it has not been tampered with",
        "",
        "The ledger is hash-sealed and externally anchored here. Verify any file in",
        "`anchors/` against the live head — if it matches, the Pi has not rewritten its past:",
        "",
        "```",
        "genus ledger anchor verify anchors/genus-anchor-<core>-<event>-<hash>.json",
        "```",
        "",
    ]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())

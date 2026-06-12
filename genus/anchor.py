"""Offline ledger anchors for externally preserving a seal head."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from genus import sealing


SCHEMA = "genus-ledger-anchor-v1"
DERIVATION = "ledger_anchor:v1"
SIGNATURE = None

_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class AnchorError(ValueError):
    pass


def create_anchor(conn, core_id: str, created_at: str | None = None) -> dict:
    core = normalize_core_id(core_id)
    if not sealing.is_active(conn):
        raise AnchorError("ledger sealing is not initialized")

    issues = sealing.verify_chain(conn)
    if issues:
        raise AnchorError("ledger seal chain is invalid: " + "; ".join(issues))

    epoch = sealing.epoch_event(conn)
    head = sealing.head(conn)
    if epoch is None or head is None:
        raise AnchorError("ledger sealing is not initialized")

    event_count = conn.execute("SELECT COUNT(*) AS count FROM event_log").fetchone()[
        "count"
    ]
    return {
        "schema": SCHEMA,
        "core_id": core,
        "created_at": created_at or _now_utc(),
        "algo": sealing.ALGO,
        "epoch_event_id": int(epoch["id"]),
        "event_count": int(event_count),
        "head_event_id": int(head["id"]),
        "head_event_type": head["event_type"],
        "head_created_at": head["created_at"],
        "head": head["seal"],
        "derivation": DERIVATION,
        "signature": SIGNATURE,
    }


def verify_anchor(conn, artifact: dict, core_id: str | None = None) -> list[str]:
    issues = validate_anchor(artifact)
    expected_core_id = None
    if core_id is not None:
        try:
            expected_core_id = normalize_core_id(core_id)
        except AnchorError as exc:
            issues.append(str(exc))

    if not issues and expected_core_id is not None:
        if artifact["core_id"] != expected_core_id:
            issues.append(
                f"anchor core_id mismatch: expected {expected_core_id}, "
                f"got {artifact['core_id']}"
            )

    if issues:
        return issues

    if not sealing.is_active(conn):
        return ["ledger sealing is not initialized"]

    chain_issues = sealing.verify_chain(conn)
    if chain_issues:
        return chain_issues

    epoch = sealing.epoch_event(conn)
    if epoch is None:
        return ["ledger sealing is not initialized"]
    if int(epoch["id"]) != artifact["epoch_event_id"]:
        issues.append(
            f"anchor epoch event mismatch: expected {artifact['epoch_event_id']}, "
            f"got {epoch['id']}"
        )

    row = conn.execute(
        """
        SELECT id, event_type, created_at, seal
        FROM event_log
        WHERE id = ?
        """,
        (artifact["head_event_id"],),
    ).fetchone()
    if row is None:
        issues.append(f"anchored head event {artifact['head_event_id']} not found")
        return issues

    if row["event_type"] != artifact["head_event_type"]:
        issues.append(
            f"anchor head event_type mismatch: expected "
            f"{artifact['head_event_type']}, got {row['event_type']}"
        )
    if row["created_at"] != artifact["head_created_at"]:
        issues.append(
            f"anchor head created_at mismatch: expected "
            f"{artifact['head_created_at']}, got {row['created_at']}"
        )
    if row["seal"] != artifact["head"]:
        issues.append("anchor head seal mismatch")

    return issues


def validate_anchor(artifact: dict) -> list[str]:
    if not isinstance(artifact, dict):
        return ["anchor must be a JSON object"]

    expected_keys = {
        "schema",
        "core_id",
        "created_at",
        "algo",
        "epoch_event_id",
        "event_count",
        "head_event_id",
        "head_event_type",
        "head_created_at",
        "head",
        "derivation",
        "signature",
    }
    keys = set(artifact)
    issues = []
    missing = sorted(expected_keys - keys)
    extra = sorted(keys - expected_keys)
    if missing:
        issues.append("anchor missing required field(s): " + ", ".join(missing))
    if extra:
        issues.append("anchor has unsupported field(s): " + ", ".join(extra))
    if missing:
        return issues

    if artifact["schema"] != SCHEMA:
        issues.append(f"anchor schema must be {SCHEMA}")
    if artifact["algo"] != sealing.ALGO:
        issues.append(f"anchor algo must be {sealing.ALGO}")
    if artifact["derivation"] != DERIVATION:
        issues.append(f"anchor derivation must be {DERIVATION}")
    if artifact["signature"] is not SIGNATURE:
        issues.append("anchor signature must be null in v1.2")

    for field in ("created_at", "head_event_type", "head_created_at"):
        if not isinstance(artifact[field], str) or not artifact[field].strip():
            issues.append(f"anchor {field} must be a non-empty string")
    try:
        normalize_core_id(artifact["core_id"])
    except AnchorError as exc:
        issues.append(str(exc))

    for field in ("epoch_event_id", "event_count", "head_event_id"):
        if not _is_non_negative_int(artifact[field]):
            issues.append(f"anchor {field} must be a non-negative integer")
    if (
        _is_non_negative_int(artifact["event_count"])
        and _is_non_negative_int(artifact["head_event_id"])
        and artifact["event_count"] < artifact["head_event_id"]
    ):
        issues.append("anchor event_count must be >= head_event_id")

    if not _is_sha256_hex(artifact["head"]):
        issues.append("anchor head must be a sha256 hex digest")

    return issues


def normalize_core_id(core_id: str) -> str:
    if not isinstance(core_id, str) or not core_id.strip():
        raise AnchorError("core_id is required")
    return core_id.strip()


def canonical_json(artifact: dict) -> str:
    return json.dumps(artifact, sort_keys=True, separators=(",", ":"))


def filename_for_anchor(artifact: dict) -> str:
    core = _FILENAME_SAFE.sub("_", artifact["core_id"]).strip("._-")
    if not core:
        core = "core"
    return f"genus-anchor-{core}-{artifact['head_event_id']}-{artifact['head'][:12]}.json"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _is_non_negative_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_sha256_hex(value) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )

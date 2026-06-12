"""Ledger sealing: a forward hash-chain plus a genesis digest.

Design boundary
---------------
Sealing is local tamper detection, not full tamper evidence against an
adaptive attacker with complete DB control. It detects accidental corruption
and lazy edits that are not re-sealed. Strong tamper evidence requires an
external anchor for ``genus ledger head``.
"""

from __future__ import annotations

import hashlib
import json


EPOCH_EVENT = "ledger_epoch_opened"
ALGO = "sha256-chain-v1"
GENESIS_SEED = "GENUS-LEDGER-GENESIS-v1"

_FIELD_SEP = "\x1f"
_RECORD_SEP = "\x1e"


def canonical_payload(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def compute_seal(prev_seal: str, event_type: str, payload_text: str) -> str:
    return _sha(_FIELD_SEP.join((prev_seal, event_type, payload_text)))


def open_epoch(conn) -> int | None:
    if is_active(conn):
        return None
    rows = _all_rows(conn)
    genesis = _genesis_over_rows(rows)
    prefix_max_id = int(rows[-1]["id"]) if rows else 0
    payload = {
        "algo": ALGO,
        "genesis_digest": genesis,
        "prefix_max_id": prefix_max_id,
        "prefix_count": len(rows),
    }
    payload_text = canonical_payload(payload)
    seal = compute_seal(genesis, EPOCH_EVENT, payload_text)
    cur = conn.execute(
        """
        INSERT INTO event_log (event_type, payload, prev_seal, seal)
        VALUES (?, ?, ?, ?)
        """,
        (EPOCH_EVENT, payload_text, genesis, seal),
    )
    return int(cur.lastrowid)


def is_active(conn) -> bool:
    return epoch_event(conn) is not None


def epoch_event(conn):
    return conn.execute(
        """
        SELECT id, payload, prev_seal, seal
        FROM event_log
        WHERE event_type = ?
        ORDER BY id
        LIMIT 1
        """,
        (EPOCH_EVENT,),
    ).fetchone()


def head(conn) -> dict | None:
    row = conn.execute(
        """
        SELECT id, event_type, created_at, prev_seal, seal
        FROM event_log
        WHERE seal IS NOT NULL
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def previous_head(conn) -> dict:
    row = head(conn)
    if row is None:
        raise ValueError("ledger sealing is not initialized")
    return row


def verify_chain(conn) -> list[str]:
    epoch = epoch_event(conn)
    if epoch is None:
        return []

    issues: list[str] = []
    try:
        meta = json.loads(epoch["payload"])
        genesis = meta["genesis_digest"]
        prefix_max_id = int(meta["prefix_max_id"])
        prefix_count = int(meta["prefix_count"])
        algo = meta["algo"]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return ["ledger_epoch_opened payload is malformed"]

    if algo != ALGO:
        issues.append(f"ledger_epoch_opened has unsupported algo {algo}")

    rows = _all_rows(conn)
    legacy = [row for row in rows if int(row["id"]) <= prefix_max_id]
    sealed = [row for row in rows if int(row["id"]) > prefix_max_id]

    if len(legacy) != prefix_count:
        issues.append("ledger genesis prefix count mismatch")
    if _genesis_over_rows(legacy) != genesis:
        issues.append("ledger genesis digest mismatch (pre-epoch history altered)")

    prev = genesis
    for row in sealed:
        row_id = int(row["id"])
        if row["prev_seal"] is None or row["seal"] is None:
            issues.append(f"event {row_id} after epoch is missing a seal")
            return issues
        if row["prev_seal"] != prev:
            issues.append(f"event {row_id} prev_seal mismatch")
            return issues
        expected = compute_seal(prev, row["event_type"], row["payload"])
        if expected != row["seal"]:
            issues.append(
                f"event {row_id} seal mismatch (content or order altered)"
            )
            return issues
        prev = row["seal"]

    return issues


def _genesis_over_rows(rows) -> str:
    if not rows:
        return _sha(GENESIS_SEED)
    records = [
        _FIELD_SEP.join(
            (
                str(row["id"]),
                row["event_type"],
                row["payload"],
                row["created_at"],
            )
        )
        for row in rows
    ]
    return _sha(_RECORD_SEP.join(records))


def _all_rows(conn):
    return conn.execute(
        """
        SELECT id, event_type, payload, created_at, prev_seal, seal
        FROM event_log
        ORDER BY id
        """
    ).fetchall()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

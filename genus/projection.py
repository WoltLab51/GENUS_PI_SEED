from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable

from genus.confidence import calculate_confidence


ACTIVE = "active"
SUPERSEDED = "superseded"
ARCHIVED = "archived"


def json_list(value: str | None) -> list[int]:
    if not value:
        return []
    parsed = json.loads(value)
    return list(parsed)


def encode_ids(values: Iterable[int]) -> str:
    return json.dumps(list(values), separators=(",", ":"))


def active_belief(conn, claim_key: str, claim_value: str | None = None):
    if claim_value is None:
        return conn.execute(
            """
            SELECT * FROM belief_projection
            WHERE claim_key = ? AND state = ?
            ORDER BY id DESC LIMIT 1
            """,
            (claim_key, ACTIVE),
        ).fetchone()
    return conn.execute(
        """
        SELECT * FROM belief_projection
        WHERE claim_key = ? AND claim_value = ? AND state = ?
        ORDER BY id DESC LIMIT 1
        """,
        (claim_key, claim_value, ACTIVE),
    ).fetchone()


def create_belief(
    conn,
    claim_key: str,
    claim_value: str,
    derivation: str,
    supporting_events: list[int],
    belief_id: int | None = None,
    created_at: str | None = None,
) -> int:
    if not derivation:
        raise ValueError("derivation must not be empty")
    if belief_id is not None:
        conn.execute(
            """
            INSERT INTO belief_projection
                (id, claim_key, claim_value, state, derivation,
                 supporting_events, created_at, last_updated_at)
            VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))
            """,
            (
                belief_id,
                claim_key,
                claim_value,
                ACTIVE,
                derivation,
                encode_ids(supporting_events),
                created_at,
                created_at,
            ),
        )
        return belief_id
    cur = conn.execute(
        """
        INSERT INTO belief_projection
            (claim_key, claim_value, state, derivation,
             supporting_events, created_at, last_updated_at)
        VALUES (?, ?, ?, ?, ?, COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))
        """,
        (
            claim_key,
            claim_value,
            ACTIVE,
            derivation,
            encode_ids(supporting_events),
            created_at,
            created_at,
        ),
    )
    return int(cur.lastrowid)


def confirm_belief(
    conn, belief_id: int, supporting_event: int, updated_at: str | None = None
) -> None:
    row = get_belief(conn, belief_id)
    supporting = json_list(row["supporting_events"])
    if supporting_event not in supporting:
        supporting.append(supporting_event)
    conn.execute(
        """
        UPDATE belief_projection
        SET supporting_events = ?,
            last_updated_at = COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        WHERE id = ?
        """,
        (encode_ids(supporting), updated_at, belief_id),
    )


def weaken_belief(
    conn, belief_id: int, contradicting_event: int, updated_at: str | None = None
) -> None:
    row = get_belief(conn, belief_id)
    contradicting = json_list(row["contradicting_events"])
    if contradicting_event not in contradicting:
        contradicting.append(contradicting_event)
    conn.execute(
        """
        UPDATE belief_projection
        SET contradicting_events = ?,
            last_updated_at = COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        WHERE id = ?
        """,
        (encode_ids(contradicting), updated_at, belief_id),
    )


def supersede_belief(
    conn, old_belief_id: int, new_belief_id: int, updated_at: str | None = None
) -> None:
    conn.execute(
        """
        UPDATE belief_projection
        SET state = ?,
            superseded_by = ?,
            last_updated_at = COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        WHERE id = ?
        """,
        (SUPERSEDED, new_belief_id, updated_at, old_belief_id),
    )


def get_belief(conn, belief_id: int):
    row = conn.execute(
        "SELECT * FROM belief_projection WHERE id = ?",
        (belief_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"belief not found: {belief_id}")
    return row


def list_active_beliefs(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM belief_projection
        WHERE state = ?
        ORDER BY claim_key, claim_value, id
        """,
        (ACTIVE,),
    ).fetchall()
    return [belief_with_confidence(conn, row) for row in rows]


def belief_with_confidence(conn, row) -> dict:
    supporting = json_list(row["supporting_events"])
    contradicting = json_list(row["contradicting_events"])
    latest_age = latest_supporting_age_seconds(conn, supporting)
    return {
        "id": row["id"],
        "claim_key": row["claim_key"],
        "claim_value": row["claim_value"],
        "state": row["state"],
        "derivation": row["derivation"],
        "supporting": len(supporting),
        "contradicting": len(contradicting),
        "confidence": calculate_confidence(
            len(supporting),
            len(contradicting),
            latest_age,
        ),
    }


def latest_supporting_age_seconds(conn, supporting_events: list[int]) -> float:
    if not supporting_events:
        return 0.0
    placeholders = ",".join("?" for _ in supporting_events)
    row = conn.execute(
        f"SELECT MAX(created_at) AS latest FROM event_log WHERE id IN ({placeholders})",
        supporting_events,
    ).fetchone()
    if row is None or row["latest"] is None:
        return 0.0
    latest = _parse_timestamp(row["latest"])
    return max(0.0, (datetime.now(timezone.utc) - latest).total_seconds())


def _parse_timestamp(value: str) -> datetime:
    normalized = value.rstrip("Z")
    return datetime.fromisoformat(normalized).replace(tzinfo=timezone.utc)


def next_belief_id(conn) -> int:
    row = conn.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'belief_projection'"
    ).fetchone()
    if row is not None:
        return int(row["seq"]) + 1
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS max_id FROM belief_projection").fetchone()
    return int(row["max_id"]) + 1


def apply_belief_created(conn, payload: dict) -> int:
    return create_belief(
        conn,
        payload["claim_key"],
        payload["claim_value"],
        payload["derivation"],
        list(payload["supporting_events"]),
        payload.get("belief_id"),
        payload.get("_event_created_at"),
    )


def apply_belief_confirmed(conn, payload: dict) -> None:
    confirm_belief(
        conn,
        int(payload["belief_id"]),
        int(payload["new_supporting_event"]),
        payload.get("_event_created_at"),
    )


def apply_belief_weakened(conn, payload: dict) -> None:
    weaken_belief(
        conn,
        int(payload["belief_id"]),
        int(payload["contradicting_event"]),
        payload.get("_event_created_at"),
    )


def apply_belief_superseded(conn, payload: dict) -> int:
    new_belief_id = create_belief(
        conn,
        payload["claim_key"],
        payload["claim_value"],
        payload["derivation"],
        list(payload["supporting_events"]),
        int(payload["new_belief_id"]),
        payload.get("_event_created_at"),
    )
    supersede_belief(
        conn,
        int(payload["old_belief_id"]),
        new_belief_id,
        payload.get("_event_created_at"),
    )
    return new_belief_id

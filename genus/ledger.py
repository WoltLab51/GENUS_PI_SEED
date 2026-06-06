from __future__ import annotations

import json


def append(conn, event_type: str, payload: dict) -> int:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    cur = conn.execute(
        "INSERT INTO event_log (event_type, payload) VALUES (?, ?)",
        (event_type, serialized),
    )
    conn.commit()
    return int(cur.lastrowid)


def tail(conn, n: int = 20) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM (
            SELECT * FROM event_log ORDER BY id DESC LIMIT ?
        )
        ORDER BY id
        """,
        (n,),
    ).fetchall()
    return [_event_dict(row) for row in rows]


def event_created_at(conn, event_id: int) -> str:
    row = conn.execute(
        "SELECT created_at FROM event_log WHERE id = ?",
        (event_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"event not found: {event_id}")
    return row["created_at"]


def _event_dict(row) -> dict:
    return {
        "id": row["id"],
        "event_type": row["event_type"],
        "payload": json.loads(row["payload"]),
        "created_at": row["created_at"],
    }

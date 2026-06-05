from __future__ import annotations

import json

from genus import projection, proposals


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


def replay(conn) -> dict:
    events = conn.execute("SELECT * FROM event_log ORDER BY id").fetchall()
    conn.execute("DELETE FROM belief_projection")
    conn.execute("DELETE FROM proposal_log")
    conn.execute(
        "DELETE FROM sqlite_sequence WHERE name IN ('belief_projection', 'proposal_log')"
    )

    for event in events:
        apply_event(conn, event)

    active_count = conn.execute(
        "SELECT COUNT(*) AS count FROM belief_projection WHERE state = 'active'"
    ).fetchone()["count"]
    proposal_count = conn.execute("SELECT COUNT(*) AS count FROM proposal_log").fetchone()[
        "count"
    ]
    conn.commit()
    return {
        "events": len(events),
        "active_beliefs": int(active_count),
        "proposals": int(proposal_count),
    }


def apply_event(conn, event) -> None:
    payload = json.loads(event["payload"])
    payload["_event_created_at"] = event["created_at"]
    event_type = event["event_type"]
    if event_type == "belief_created":
        projection.apply_belief_created(conn, payload)
    elif event_type == "belief_confirmed":
        projection.apply_belief_confirmed(conn, payload)
    elif event_type == "belief_weakened":
        projection.apply_belief_weakened(conn, payload)
    elif event_type == "belief_superseded":
        projection.apply_belief_superseded(conn, payload)
    elif event_type == "proposal_created":
        proposals.apply_proposal_created(conn, payload)


def _event_dict(row) -> dict:
    return {
        "id": row["id"],
        "event_type": row["event_type"],
        "payload": json.loads(row["payload"]),
        "created_at": row["created_at"],
    }

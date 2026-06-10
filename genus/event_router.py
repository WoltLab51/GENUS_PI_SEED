from __future__ import annotations

import json

from genus import inquiries, projection, proposals


def replay(conn) -> dict:
    events = conn.execute("SELECT * FROM event_log ORDER BY id").fetchall()
    conn.execute("DELETE FROM inquiry_log")
    conn.execute("DELETE FROM proposal_log")
    conn.execute("DELETE FROM belief_projection")
    conn.execute(
        """
        DELETE FROM sqlite_sequence
        WHERE name IN ('inquiry_log', 'proposal_log', 'belief_projection')
        """
    )

    for event in events:
        apply_event(conn, event)

    active_count = conn.execute(
        "SELECT COUNT(*) AS count FROM belief_projection WHERE state = 'active'"
    ).fetchone()["count"]
    proposal_count = conn.execute("SELECT COUNT(*) AS count FROM proposal_log").fetchone()[
        "count"
    ]
    inquiry_count = conn.execute("SELECT COUNT(*) AS count FROM inquiry_log").fetchone()[
        "count"
    ]
    conn.commit()
    return {
        "events": len(events),
        "active_beliefs": int(active_count),
        "proposals": int(proposal_count),
        "inquiries": int(inquiry_count),
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
    elif event_type == "proposal_reviewed":
        proposals.apply_proposal_reviewed(conn, payload)
    elif event_type == "inquiry_created":
        inquiries.apply_inquiry_created(conn, payload)
    elif event_type == "inquiry_resolved":
        inquiries.apply_inquiry_resolved(conn, payload)

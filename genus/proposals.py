from __future__ import annotations

import json


def create_proposal(
    conn,
    proposal_type: str,
    claim_key: str,
    claim_value: str,
    source_belief: int | None,
    source_event: int,
    payload: dict,
    proposal_id: int | None = None,
    created_at: str | None = None,
) -> int:
    serialized_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if proposal_id is not None:
        conn.execute(
            """
            INSERT INTO proposal_log
                (id, proposal_type, claim_key, claim_value, source_belief,
                 source_event, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?,
                    COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))
            """,
            (
                proposal_id,
                proposal_type,
                claim_key,
                claim_value,
                source_belief,
                source_event,
                serialized_payload,
                created_at,
            ),
        )
        return proposal_id
    cur = conn.execute(
        """
        INSERT INTO proposal_log
            (proposal_type, claim_key, claim_value, source_belief,
             source_event, payload, created_at)
        VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))
        """,
        (
            proposal_type,
            claim_key,
            claim_value,
            source_belief,
            source_event,
            serialized_payload,
            created_at,
        ),
    )
    return int(cur.lastrowid)


def create_resource_proposal_for_sustained_high(conn, trigger_belief_id: int, trigger_event_id: int) -> int:
    return create_proposal(
        conn,
        proposal_type="ResourceProposal",
        claim_key="system.load",
        claim_value="high",
        source_belief=trigger_belief_id,
        source_event=trigger_event_id,
        payload={
            "description": "CPU load is sustained high. Investigate resource pressure.",
            "observed_pattern": "system.load: high",
            "action_required": False,
            "review_recommended": True,
        },
    )


def create_resource_proposal_for_contradiction(conn, trigger_belief_id: int, trigger_event_id: int) -> int:
    return create_proposal(
        conn,
        proposal_type="ResourceProposal",
        claim_key="system.load",
        claim_value="high",
        source_belief=trigger_belief_id,
        source_event=trigger_event_id,
        payload={
            "description": "CPU load was high, then dropped. Investigate cause.",
            "observed_pattern": "system.load: high -> normal",
            "action_required": False,
            "review_recommended": True,
        },
    )


def list_proposals(conn, include_all: bool = False) -> list[dict]:
    if include_all:
        rows = conn.execute("SELECT * FROM proposal_log ORDER BY id").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM proposal_log WHERE state = 'pending' ORDER BY id"
        ).fetchall()
    return [dict(row) for row in rows]


def next_proposal_id(conn) -> int:
    row = conn.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'proposal_log'"
    ).fetchone()
    if row is not None:
        return int(row["seq"]) + 1
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS max_id FROM proposal_log").fetchone()
    return int(row["max_id"]) + 1


def proposal_payload_for_sustained_high() -> dict:
    return {
        "description": "CPU load is sustained high. Investigate resource pressure.",
        "observed_pattern": "system.load: high",
        "action_required": False,
        "review_recommended": True,
    }


def proposal_payload_for_contradiction() -> dict:
    return {
        "description": "CPU load was high, then dropped. Investigate cause.",
        "observed_pattern": "system.load: high -> normal",
        "action_required": False,
        "review_recommended": True,
    }


def apply_proposal_created(conn, payload: dict) -> int:
    return create_proposal(
        conn,
        proposal_type=payload["proposal_type"],
        claim_key=payload["claim_key"],
        claim_value=payload["claim_value"],
        source_belief=payload.get("source_belief"),
        source_event=int(payload["source_event"]),
        payload=dict(payload["payload"]),
        proposal_id=int(payload["proposal_id"]),
        created_at=payload.get("_event_created_at"),
    )

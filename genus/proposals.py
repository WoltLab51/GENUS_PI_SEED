from __future__ import annotations

import json

from genus import ledger


PROPOSAL_TYPE = "ResourceProposal"
LOAD_CLAIM_KEY = "system.load"
HIGH_CLAIM_VALUE = "high"
PENDING = "pending"
ACCEPTED = "accepted"
REJECTED = "rejected"
DECISIONS = {ACCEPTED, REJECTED}


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


def list_proposals(conn, include_all: bool = False) -> list[dict]:
    if include_all:
        rows = conn.execute("SELECT * FROM proposal_log ORDER BY id").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM proposal_log WHERE state = ? ORDER BY id",
            (PENDING,),
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


def record_resource_proposal_for_sustained_high(
    conn,
    trigger_belief_id: int,
    trigger_event_id: int,
    claim_key: str = LOAD_CLAIM_KEY,
) -> int:
    return record_proposal_created_event(
        conn,
        proposal_id=next_proposal_id(conn),
        proposal_type=PROPOSAL_TYPE,
        claim_key=claim_key,
        claim_value=HIGH_CLAIM_VALUE,
        source_belief=trigger_belief_id,
        source_event=trigger_event_id,
        payload=proposal_payload_for_sustained_high(claim_key),
    )


def record_resource_proposal_for_contradiction(
    conn,
    trigger_belief_id: int,
    trigger_event_id: int,
    claim_key: str = LOAD_CLAIM_KEY,
) -> int:
    return record_proposal_created_event(
        conn,
        proposal_id=next_proposal_id(conn),
        proposal_type=PROPOSAL_TYPE,
        claim_key=claim_key,
        claim_value=HIGH_CLAIM_VALUE,
        source_belief=trigger_belief_id,
        source_event=trigger_event_id,
        payload=proposal_payload_for_contradiction(claim_key),
    )


def record_proposal_created_event(
    conn,
    proposal_id: int,
    proposal_type: str,
    claim_key: str,
    claim_value: str,
    source_belief: int | None,
    source_event: int,
    payload: dict,
) -> int:
    event_payload = {
        "proposal_id": proposal_id,
        "proposal_type": proposal_type,
        "claim_key": claim_key,
        "claim_value": claim_value,
        "source_belief": source_belief,
        "source_event": source_event,
        "payload": payload,
        "reason": payload["description"],
    }
    event_id = ledger.append(conn, "proposal_created", event_payload)
    event_payload["_event_created_at"] = ledger.event_created_at(conn, event_id)
    apply_proposal_created(conn, event_payload)
    return event_id


def record_proposal_reviewed_event(
    conn, proposal_id: int, decision: str, note: str = ""
) -> int:
    proposal = get_proposal(conn, proposal_id)
    if proposal["state"] != PENDING:
        raise ValueError("already reviewed")
    if decision not in DECISIONS:
        raise ValueError("decision must be accepted or rejected")

    event_payload = {
        "proposal_id": proposal_id,
        "decision": decision,
        "note": note,
    }
    event_id = ledger.append(conn, "proposal_reviewed", event_payload)
    event_payload["_event_created_at"] = ledger.event_created_at(conn, event_id)
    apply_proposal_reviewed(conn, event_payload)
    return event_id


def review_proposal_governed(
    conn,
    proposal_id: int,
    decision: str,
    note: str = "",
    override: bool = False,
) -> dict:
    from genus import governance

    verdict = governance.evaluate_proposal_review(
        conn,
        proposal_id,
        decision,
        override,
    )
    if verdict["decision"] == governance.BLOCKED:
        return verdict
    event_id = record_proposal_reviewed_event(conn, proposal_id, decision, note)
    verdict["review_event_id"] = event_id
    return verdict


def proposal_payload_for_sustained_high(claim_key: str = LOAD_CLAIM_KEY) -> dict:
    return {
        "description": f"{claim_key} is sustained high. Investigate resource pressure.",
        "observed_pattern": f"{claim_key}: high",
        "action_required": False,
        "review_recommended": True,
    }


def proposal_payload_for_contradiction(claim_key: str = LOAD_CLAIM_KEY) -> dict:
    return {
        "description": f"{claim_key} was high, then dropped. Investigate cause.",
        "observed_pattern": f"{claim_key}: high -> normal",
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


def apply_proposal_reviewed(conn, payload: dict) -> None:
    decision = payload["decision"]
    if decision not in DECISIONS:
        raise ValueError("decision must be accepted or rejected")
    conn.execute(
        """
        UPDATE proposal_log
        SET state = ?,
            decision = ?,
            reviewed_at = COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        WHERE id = ?
        """,
        (decision, decision, payload.get("_event_created_at"), int(payload["proposal_id"])),
    )


def get_proposal(conn, proposal_id: int):
    row = conn.execute(
        "SELECT * FROM proposal_log WHERE id = ?",
        (proposal_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"proposal not found: {proposal_id}")
    return row

from __future__ import annotations

import json

from genus import ledger


INQUIRY_TYPE = "CauseInquiry"
QUESTION_KEY = "cause.changed_state"
OPEN = "open"
RESOLVED = "resolved"


def create_inquiry(
    conn,
    inquiry_type: str,
    claim_key: str,
    source_belief: int,
    source_event: int,
    question_key: str,
    payload: dict,
    inquiry_id: int | None = None,
    created_at: str | None = None,
) -> int:
    serialized_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if inquiry_id is not None:
        conn.execute(
            """
            INSERT INTO inquiry_log
                (id, inquiry_type, claim_key, source_belief, source_event,
                 question_key, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?,
                    COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))
            """,
            (
                inquiry_id,
                inquiry_type,
                claim_key,
                source_belief,
                source_event,
                question_key,
                serialized_payload,
                created_at,
            ),
        )
        return inquiry_id
    cur = conn.execute(
        """
        INSERT INTO inquiry_log
            (inquiry_type, claim_key, source_belief, source_event,
             question_key, payload, created_at)
        VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))
        """,
        (
            inquiry_type,
            claim_key,
            source_belief,
            source_event,
            question_key,
            serialized_payload,
            created_at,
        ),
    )
    return int(cur.lastrowid)


def next_inquiry_id(conn) -> int:
    row = conn.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'inquiry_log'"
    ).fetchone()
    if row is not None:
        return int(row["seq"]) + 1
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS max_id FROM inquiry_log").fetchone()
    return int(row["max_id"]) + 1


def record_cause_inquiry_for_contradiction(
    conn,
    claim_key: str,
    source_belief: int,
    source_event: int,
) -> int:
    return record_inquiry_created_event(
        conn,
        inquiry_id=next_inquiry_id(conn),
        inquiry_type=INQUIRY_TYPE,
        claim_key=claim_key,
        source_belief=source_belief,
        source_event=source_event,
        question_key=QUESTION_KEY,
        payload={
            "changed_from": "high",
            "changed_to": "normal",
            "review_recommended": True,
        },
    )


def record_inquiry_created_event(
    conn,
    inquiry_id: int,
    inquiry_type: str,
    claim_key: str,
    source_belief: int,
    source_event: int,
    question_key: str,
    payload: dict,
) -> int:
    event_payload = {
        "inquiry_id": inquiry_id,
        "inquiry_type": inquiry_type,
        "claim_key": claim_key,
        "source_belief": source_belief,
        "source_event": source_event,
        "question_key": question_key,
        "payload": payload,
        "state": OPEN,
    }
    event_id = ledger.append(conn, "inquiry_created", event_payload)
    event_payload["_event_created_at"] = ledger.event_created_at(conn, event_id)
    apply_inquiry_created(conn, event_payload)
    return event_id


def apply_inquiry_created(conn, payload: dict) -> int:
    return create_inquiry(
        conn,
        inquiry_type=payload["inquiry_type"],
        claim_key=payload["claim_key"],
        source_belief=int(payload["source_belief"]),
        source_event=int(payload["source_event"]),
        question_key=payload["question_key"],
        payload=dict(payload["payload"]),
        inquiry_id=int(payload["inquiry_id"]),
        created_at=payload.get("_event_created_at"),
    )


def record_inquiry_resolved_event(conn, inquiry_id: int, answer: str) -> int:
    inquiry = get_inquiry(conn, inquiry_id)
    if inquiry["state"] != OPEN:
        raise ValueError("already resolved")
    if not answer.strip():
        raise ValueError("answer must not be empty")

    event_payload = {
        "inquiry_id": inquiry_id,
        "answer": answer,
    }
    event_id = ledger.append(conn, "inquiry_resolved", event_payload)
    event_payload["_event_created_at"] = ledger.event_created_at(conn, event_id)
    apply_inquiry_resolved(conn, event_payload)
    return event_id


def apply_inquiry_resolved(conn, payload: dict) -> None:
    conn.execute(
        """
        UPDATE inquiry_log
        SET state = ?,
            answer = ?,
            resolved_at = COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        WHERE id = ?
        """,
        (
            RESOLVED,
            payload["answer"],
            payload.get("_event_created_at"),
            int(payload["inquiry_id"]),
        ),
    )


def list_inquiries(conn, include_all: bool = False) -> list[dict]:
    if include_all:
        rows = conn.execute("SELECT * FROM inquiry_log ORDER BY id").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM inquiry_log WHERE state = ? ORDER BY id",
            (OPEN,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_inquiry(conn, inquiry_id: int):
    row = conn.execute(
        "SELECT * FROM inquiry_log WHERE id = ?",
        (inquiry_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"inquiry not found: {inquiry_id}")
    return row

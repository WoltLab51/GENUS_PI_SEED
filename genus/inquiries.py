from __future__ import annotations

import json

from genus import ledger


INQUIRY_TYPE = "CauseInquiry"
QUESTION_KEY = "cause.changed_state"
SOURCE_CONTRADICTION_TYPE = "SourceContradiction"
SOURCE_CONTRADICTION_QUESTION = "source.contradiction"
ABSTRAKTION_INQUIRY_TYPE = "AbstraktionInquiry"   # die Rückkopplung selbst geprägter Begriffe
ABSTRAKTION_QUESTION = "abstraktion.rueckkopplung"
OPEN = "open"
RESOLVED = "resolved"
RECONCILED_EVENT = "inquiries_reconciled"


def create_inquiry(
    conn,
    inquiry_type: str,
    claim_key: str,
    source_belief: int | None,
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


def record_source_contradiction_inquiry(
    conn,
    claim_key: str,
    source_event: int,
    payload: dict,
) -> int:
    """Raise a claim-anchored inquiry: trusted sources disagree about this claim.

    A metric claim need not have a categorical belief, so there is nothing to anchor a
    belief to -- ``source_belief`` is ``None`` and the inquiry hangs on the claim and the
    assertion event that exposed the conflict. The seed of the teacher-loop: GENUS flags
    a disagreement it cannot settle from its own sources.
    """
    return record_inquiry_created_event(
        conn,
        inquiry_id=next_inquiry_id(conn),
        inquiry_type=SOURCE_CONTRADICTION_TYPE,
        claim_key=claim_key,
        source_belief=None,
        source_event=source_event,
        question_key=SOURCE_CONTRADICTION_QUESTION,
        payload=payload,
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
    source_belief = payload["source_belief"]
    return create_inquiry(
        conn,
        inquiry_type=payload["inquiry_type"],
        claim_key=payload["claim_key"],
        source_belief=int(source_belief) if source_belief is not None else None,
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


def record_inquiries_reconciled_event(
    conn, inquiry_ids: list[int], answer: str
) -> int | None:
    """Resolve a mechanically proven batch with one compact, replayable event.

    A reconciliation is not a human answer. It is limited to false alarms or
    superseded duplicate questions that can be decided from structural invariants.
    Keeping one event avoids turning backlog cleanup into tens of thousands of new
    ledger entries while preserving the exact affected inquiry ids.
    """
    ids = sorted({int(inquiry_id) for inquiry_id in inquiry_ids})
    if not ids:
        return None
    if not answer.strip():
        raise ValueError("answer must not be empty")
    payload = {"inquiry_ids": ids, "answer": answer}
    event_id = ledger.append(conn, RECONCILED_EVENT, payload)
    payload["_event_created_at"] = ledger.event_created_at(conn, event_id)
    apply_inquiries_reconciled(conn, payload)
    return event_id


def apply_inquiries_reconciled(conn, payload: dict) -> None:
    ids = sorted({int(value) for value in payload["inquiry_ids"]})
    answer = str(payload["answer"]).strip()
    if not answer:
        raise ValueError("answer must not be empty")
    resolved_at = payload.get("_event_created_at")
    conn.executemany(
        """
        UPDATE inquiry_log
        SET state = ?, answer = ?,
            resolved_at = COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        WHERE id = ? AND state = ?
        """,
        [(RESOLVED, answer, resolved_at, inquiry_id, OPEN) for inquiry_id in ids],
    )


def reconcile(
    conn, *, dry_run: bool = False, repair_cycles: bool = False
) -> dict:
    """Close only inquiries whose answer follows mechanically from current rules.

    Two live failure modes are covered: acyclicity alarms for predicates that are
    not declared hierarchical, and multiple still-open StabilityInquiry rows for
    one claim. The newest stability question remains actionable. Real hierarchy
    cycles and genuine source disagreements are never auto-resolved here.
    """
    from genus import inference, projection

    false_acyclicity: list[int] = []
    hierarchy_cycles: list[tuple[int, dict]] = []
    rows = conn.execute(
        "SELECT id, payload FROM inquiry_log "
        "WHERE state = ? AND inquiry_type = ? ORDER BY id",
        (OPEN, SOURCE_CONTRADICTION_TYPE),
    ).fetchall()
    for row in rows:
        try:
            detail = json.loads(row["payload"])
        except (TypeError, json.JSONDecodeError):
            continue
        if (
            detail.get("kind") == "acyclicity_violation"
            and detail.get("predicate") not in inference.ACYCLIC_PREDICATES
        ):
            false_acyclicity.append(int(row["id"]))
        elif (
            detail.get("kind") == "acyclicity_violation"
            and detail.get("predicate") in inference.ACYCLIC_PREDICATES
        ):
            hierarchy_cycles.append((int(row["id"]), detail))

    duplicate_stability: list[int] = []
    groups = conn.execute(
        """
        SELECT claim_key, GROUP_CONCAT(id) AS ids
        FROM inquiry_log
        WHERE state = ? AND inquiry_type = 'StabilityInquiry'
        GROUP BY claim_key HAVING COUNT(*) > 1
        """,
        (OPEN,),
    ).fetchall()
    for group in groups:
        ids = sorted(int(value) for value in group["ids"].split(","))
        duplicate_stability.extend(ids[:-1])

    repaired_cycle_ids = [inquiry_id for inquiry_id, _ in hierarchy_cycles] if repair_cycles else []
    resolved = sorted(set(false_acyclicity + duplicate_stability + repaired_cycle_ids))
    event_id = None
    if resolved and not dry_run:
        if repair_cycles:
            seen_edges: set[tuple[str, str, str]] = set()
            for _, detail in hierarchy_cycles:
                edge = (
                    str(detail["subject"]),
                    str(detail["predicate"]),
                    str(detail["object"]),
                )
                if edge in seen_edges:
                    continue
                seen_edges.add(edge)
                retraction = {
                    "subject": edge[0], "predicate": edge[1], "object": edge[2],
                    "source": None,
                    "reason": "maintenance: repair historical acyclicity violation",
                }
                ledger.append(conn, "relation_retracted", retraction)
                projection.apply_relation_retracted(conn, retraction)
        event_id = record_inquiries_reconciled_event(
            conn,
            resolved,
            "auto: false acyclicity alarm or superseded duplicate stability question",
        )
        conn.commit()
    return {
        "resolved": resolved,
        "false_acyclicity": len(false_acyclicity),
        "duplicate_stability": len(duplicate_stability),
        "repairable_cycles": len(hierarchy_cycles),
        "repaired_cycles": len(repaired_cycle_ids),
        "event_id": event_id,
        "dry_run": dry_run,
    }


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
